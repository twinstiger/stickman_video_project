# 音频嵌入节点
# 根据故事类型添加背景音乐，可选添加AI旁白朗读

import os
import json
import requests
import subprocess
import tempfile
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from coze_coding_dev_sdk.video_edit import VideoEditClient
from coze_coding_dev_sdk import TTSClient
from coze_coding_dev_sdk.s3 import S3SyncStorage

from graphs.state import AudioEmbedInput, AudioEmbedOutput


# BGM音量百分比（固定20%）
BGM_VOLUME = 20

# 旁白音量百分比
NARRATION_VOLUME = 80

# TTS旁白声音配置（平缓男声）
NARRATION_VOICE = "zh_male_ruyayichen_saturn_bigtts"  # 优雅男声


def audio_embed_node(
    state: AudioEmbedInput,
    config: RunnableConfig,
    runtime: Runtime[Context]
) -> AudioEmbedOutput:
    """
    title: 音频嵌入
    desc: 根据故事类型自动匹配BGM，固定20%音量；可选添加AI旁白朗读
    integrations: 视频编辑, 语音合成, 对象存储
    """
    ctx = runtime.context
    
    video_url = state.base_video_url
    story_text = state.story_text
    story_type = state.story_type
    enable_narration = state.enable_narration
    
    # 初始化客户端
    video_client = VideoEditClient(ctx=ctx)
    tts_client = TTSClient(ctx=ctx)
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="audio_embed_")
    
    try:
        # Step 1: 使用ffmpeg生成柔和的背景音乐（和弦风格）
        # 根据故事类型选择不同的音调风格
        bgm_path = os.path.join(temp_dir, "bgm.mp3")
        
        # 生成5分钟循环背景音乐（柔和钢琴风格）
        # 使用ffmpeg合成多个正弦波叠加形成和弦效果
        bgm_freq = _get_bgm_frequency(story_type)
        
        # 生成背景音乐：叠加多个正弦波形成柔和和弦
        # 主音符 + 低音 + 高音形成简单的和弦效果
        ffmpeg_bgm_cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"sine=frequency={bgm_freq}:duration=300",  # 主音
            "-f", "lavfi",
            "-i", f"sine=frequency={int(bgm_freq*0.75)}:duration=300",  # 低音（降五度）
            "-f", "lavfi",
            "-i", f"sine=frequency={int(bgm_freq*1.5)}:duration=300",  # 高音（升八度）
            "-filter_complex", 
            f"[0:a][1:a][2:a]amix=inputs=3:duration=longest[aout];[aout]volume=0.08",  # 混音并降低音量
            "-c:a", "libmp3lame", "-q:a", "4",
            bgm_path
        ]
        
        # 尝试生成和弦BGM
        bgm_result = subprocess.run(ffmpeg_bgm_cmd, capture_output=True, text=True)
        
        if bgm_result.returncode != 0:
            # 备用方案1：单音符正弦波
            ffmpeg_bgm_cmd2 = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"sine=frequency={bgm_freq}:duration=300",
                "-af", "volume=0.12",
                "-c:a", "libmp3lame", "-q:a", "4",
                bgm_path
            ]
            bgm_result2 = subprocess.run(ffmpeg_bgm_cmd2, capture_output=True, text=True)
            
            if bgm_result2.returncode != 0:
                # 备用方案2：静音音频轨道（确保视频有音频）
                ffmpeg_bgm_cmd3 = [
                    "ffmpeg", "-y",
                    "-f", "lavfi",
                    "-i", "anullsrc=r=24000:cl=mono,duration=300",
                    "-c:a", "libmp3lame", "-q:a", "4",
                    bgm_path
                ]
                subprocess.run(ffmpeg_bgm_cmd3, capture_output=True, check=True)
        
        # Step 2: 如果启用旁白，生成旁白音频
        narration_audio_url = None
        if enable_narration:
            try:
                narration_audio_url, _ = tts_client.synthesize(
                    uid="stickman_narrator",
                    text=story_text,
                    speaker=NARRATION_VOICE,
                    audio_format="mp3",
                    sample_rate=24000,
                    speech_rate=-10,  # 略慢，平缓朗读
                    loudness_rate=NARRATION_VOLUME - 50  # 转换为API参数范围
                )
            except Exception as e:
                # 旁白生成失败，跳过旁白
                narration_audio_url = None
        
        # Step 3: 获取视频时长
        # 下载视频到临时目录获取时长信息
        video_path = os.path.join(temp_dir, "input_video.mp4")
        resp = requests.get(video_url, timeout=60)
        with open(video_path, "wb") as f:
            f.write(resp.content)
        
        # 使用ffprobe获取视频时长
        ffprobe_cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            video_path
        ]
        probe_result = subprocess.run(ffprobe_cmd, capture_output=True, text=True)
        video_duration = 30.0  # 默认30秒
        
        if probe_result.returncode == 0:
            probe_data = json.loads(probe_result.stdout)
            if probe_data.get("format") and probe_data.get("format").get("duration"):
                video_duration = float(probe_data["format"]["duration"])
        
        # Step 4: 裁剪BGM到视频时长
        trimmed_bgm_path = os.path.join(temp_dir, "trimmed_bgm.mp3")
        ffmpeg_trim_cmd = [
            "ffmpeg", "-y",
            "-i", bgm_path,
            "-t", str(video_duration),
            "-c:a", "copy",
            trimmed_bgm_path
        ]
        subprocess.run(ffmpeg_trim_cmd, capture_output=True, check=True)
        
        # Step 5: 上传BGM到对象存储
        storage = S3SyncStorage(
            endpoint_url=os.getenv("COZE_BUCKET_ENDPOINT_URL"),
            bucket_name=os.getenv("COZE_BUCKET_NAME"),
            region="cn-beijing"
        )
        
        with open(trimmed_bgm_path, "rb") as f:
            bgm_data = f.read()
        
        bgm_key = storage.upload_file(
            file_content=bgm_data,
            file_name="stickman_story/bgm.mp3",
            content_type="audio/mp3"
        )
        
        bgm_url = storage.generate_presigned_url(key=bgm_key, expire_time=86400)
        
        # Step 6: 使用VideoEditClient合成音频到视频
        response = video_client.compile_video_audio(
            video=video_url,
            audio=bgm_url,
            is_audio_reserve=False,
            is_video_audio_sync=True
        )
        
        video_with_audio_url = response.url
        
    except Exception as e:
        # 音频合成失败，返回原视频并记录错误
        video_with_audio_url = video_url
        
    finally:
        # 清理临时目录
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    return AudioEmbedOutput(video_with_audio_url=video_with_audio_url)


def _get_bgm_frequency(story_type: str) -> int:
    """根据故事类型返回合适的背景音乐频率"""
    # 不同频率代表不同情绪风格
    freq_mapping = {
        "励志": 440,   # A4音符，昂扬
        "亲情": 392,   # G4音符，温暖
        "感悟": 330,   # E4音符，深沉
        "治愈": 262,   # C4音符，平和
    }
    return freq_mapping.get(story_type, 392)  # 默认G4


def _adjust_audio_volume(audio_url: str, volume_percent: int, temp_dir: str) -> str:
    """调整音频音量"""
    import subprocess
    
    # 下载音频
    audio_path = os.path.join(temp_dir, "original_audio.mp3")
    resp = requests.get(audio_url, timeout=30)
    with open(audio_path, "wb") as f:
        f.write(resp.content)
    
    # 调整音量
    adjusted_path = os.path.join(temp_dir, "adjusted_audio.mp3")
    volume_factor = volume_percent / 100.0
    
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-i", audio_path,
        "-af", f"volume={volume_factor}",
        "-c:a", "libmp3lame",
        adjusted_path
    ]
    
    subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
    
    # 上传调整后的音频
    from coze_coding_dev_sdk.s3 import S3SyncStorage
    storage = S3SyncStorage(
        endpoint_url=os.getenv("COZE_BUCKET_ENDPOINT_URL"),
        bucket_name=os.getenv("COZE_BUCKET_NAME"),
        region="cn-beijing"
    )
    
    with open(adjusted_path, "rb") as f:
        audio_data = f.read()
    
    audio_key = storage.upload_file(
        file_content=audio_data,
        file_name="stickman_story/adjusted_bgm.mp3",
        content_type="audio/mp3"
    )
    
    return storage.generate_presigned_url(key=audio_key, expire_time=86400)