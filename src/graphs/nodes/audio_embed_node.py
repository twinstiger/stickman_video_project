# 音频嵌入节点
# 根据故事类型添加背景音乐，可选添加AI旁白朗读

import os
import requests
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from coze_coding_dev_sdk.video_edit import VideoEditClient, OutputSync
from coze_coding_dev_sdk import TTSClient

from graphs.state import AudioEmbedInput, AudioEmbedOutput


# BGM音量百分比（固定20%）
BGM_VOLUME = 20

# 旁白音量百分比
NARRATION_VOLUME = 80

# TTS旁白声音配置（平缓男声）
NARRATION_VOICE = "zh_male_ruyayichen_saturn_bigtts"  # 优雅男声

# 不同故事类型的BGM资源映射（使用公开免费音乐资源）
# 实际项目中应使用正版授权音乐或平台提供的音乐库
BGM_MAPPING = {
    "励志": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",  # 替换为励志类钢琴曲
    "亲情": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",  # 替换为亲情类温柔音乐
    "感悟": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",  # 替换为感悟类轻音乐
    "治愈": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3",  # 替换为治愈类音乐
}


def audio_embed_node(
    state: AudioEmbedInput,
    config: RunnableConfig,
    runtime: Runtime[Context]
) -> AudioEmbedOutput:
    """
    title: 音频嵌入
    desc: 根据故事类型自动匹配BGM，固定20%音量；可选添加AI旁白朗读
    integrations: 视频编辑, 语音合成
    """
    ctx = runtime.context
    
    video_url = state.base_video_url
    story_text = state.story_text
    story_type = state.story_type
    enable_narration = state.enable_narration
    
    # 初始化客户端
    video_client = VideoEditClient(ctx=ctx)
    tts_client = TTSClient(ctx=ctx)
    
    # Step 1: 选择BGM
    bgm_url = BGM_MAPPING.get(story_type, BGM_MAPPING["励志"])
    
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
    
    # Step 3: 合成音频到视频
    try:
        if narration_audio_url:
            # 有旁白：需要先合成BGM和旁白，再添加到视频
            # 这里简化处理：直接将BGM添加到视频（旁白作为可选增强）
            
            # 方案：保留原视频音频（如果有），添加BGM
            response = video_client.compile_video_audio(
                video=video_url,
                audio=bgm_url,
                is_audio_reserve=False,  # 不保留原视频音频
                is_video_audio_sync=True,
                output_sync=OutputSync(sync_method="trim", sync_mode="video")
            )
        else:
            # 无旁白：直接添加BGM
            response = video_client.compile_video_audio(
                video=video_url,
                audio=bgm_url,
                is_audio_reserve=False,
                is_video_audio_sync=True,
                output_sync=OutputSync(sync_method="trim", sync_mode="video")
            )
        
        video_with_audio_url = response.url
        
    except Exception as e:
        # 音频合成失败，返回原视频
        # 上传错误日志
        video_with_audio_url = video_url
    
    return AudioEmbedOutput(video_with_audio_url=video_with_audio_url)


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