# 视频合成节点（本地ffmpeg处理）
# 使用ffmpeg直接合成视频、字幕、音频，避免URL访问问题

import os
import json
import subprocess
import tempfile
import requests
from typing import List
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from coze_coding_dev_sdk.s3 import S3SyncStorage
from coze_coding_dev_sdk import TTSClient

from graphs.state import VideoComposeInput, VideoComposeOutput


# 每张图片停留时间（秒）
IMAGE_DURATION = 3.0

# BGM音量
BGM_VOLUME = 0.15

# 字幕样式参数
FONT_FILE = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"  # 系统中文字体（粗黑体）
FONT_SIZE = 42
FONT_COLOR = "white"
BORDER_COLOR = "black"
BORDER_WIDTH = 3
BACKGROUND_COLOR = "black@0.4"  # 半透明黑色（40%不透明度）


def video_compose_node(
    state: VideoComposeInput,
    config: RunnableConfig,
    runtime: Runtime[Context]
) -> VideoComposeOutput:
    """
    title: 视频合成（完整版）
    desc: 使用ffmpeg本地合成视频，包含字幕和BGM，一次性完成所有处理
    integrations: 对象存储
    """
    ctx = runtime.context
    
    image_urls: List[str] = state.image_urls
    sentences: List[str] = state.sentences
    story_type: str = state.story_type if hasattr(state, 'story_type') else "励志"
    story_text: str = state.story_text if hasattr(state, 'story_text') else ""
    enable_narration: bool = state.enable_narration if hasattr(state, 'enable_narration') else False
    
    if not image_urls:
        raise Exception("没有可用的图片进行视频合成")
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="stickman_full_")
    
    try:
        # Step 1: 下载所有图片
        frame_paths: List[str] = []
        for i, url in enumerate(image_urls):
            img_path = os.path.join(temp_dir, f"frame_{i:03d}.png")
            resp = requests.get(url, timeout=30)
            with open(img_path, "wb") as f:
                f.write(resp.content)
            frame_paths.append(img_path)
        
        # Step 2: 创建视频列表文件
        list_file = os.path.join(temp_dir, "frames.txt")
        with open(list_file, "w") as f:
            for path in frame_paths:
                f.write(f"file '{path}'\n")
                f.write(f"duration {IMAGE_DURATION}\n")
            if frame_paths:
                f.write(f"file '{frame_paths[-1]}'\n")
        
        # Step 3: 生成字幕ASS/SSA格式（支持样式）
        subtitle_file = os.path.join(temp_dir, "subtitles.ass")
        _create_ass_subtitle(subtitle_file, sentences, len(frame_paths))
        
        # Step 4: 生成BGM音频
        bgm_file = os.path.join(temp_dir, "bgm.mp3")
        bgm_freq = _get_bgm_frequency(story_type)
        _generate_bgm(bgm_file, bgm_freq, len(sentences) * IMAGE_DURATION)
        
        # Step 5: 生成旁白音频（如果启用）
        narration_file = None
        if enable_narration and story_text:
            narration_file = os.path.join(temp_dir, "narration.mp3")
            try:
                tts_client = TTSClient(ctx=ctx)
                narration_url, _ = tts_client.synthesize(
                    uid="stickman_narrator",
                    text=story_text,
                    speaker="zh_male_ruyayichen_saturn_bigtts",
                    audio_format="mp3",
                    sample_rate=24000,
                    speech_rate=-10,
                    loudness_rate=30
                )
                resp = requests.get(narration_url, timeout=60)
                with open(narration_file, "wb") as f:
                    f.write(resp.content)
            except Exception:
                narration_file = None
        
        # Step 6: 使用ffmpeg一次性合成视频+字幕+音频
        output_video = os.path.join(temp_dir, "final_video.mp4")
        
        # 构建ffmpeg滤镜：添加字幕
        # 使用drawtext滤镜或ass滤镜
        subtitle_filter = f"ass='{subtitle_file}'"
        
        # 构建音频输入和混合
        audio_inputs = []
        audio_filter_parts = []
        
        # BGM输入
        audio_inputs.extend([
            "-i", bgm_file
        ])
        
        # 如果有旁白，添加旁白输入
        if narration_file:
            audio_inputs.extend([
                "-i", narration_file
            ])
            # 混合BGM和旁白
            audio_filter_parts.append("[1:a]volume=0.15[bgm]")
            audio_filter_parts.append("[2:a]volume=0.8[narration]")
            audio_filter_parts.append("[bgm][narration]amix=inputs=2:duration=longest[aout]")
            audio_filter = ";".join(audio_filter_parts)
        else:
            # 只有BGM
            audio_filter_parts.append("[1:a]volume=0.15[aout]")
            audio_filter = ";".join(audio_filter_parts)
        
        # ffmpeg完整命令
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", list_file,  # 图片序列输入
        ]
        
        # 添加音频输入
        ffmpeg_cmd.extend(audio_inputs)
        
        # 视频滤镜：字幕 + 缩放
        ffmpeg_cmd.extend([
            "-vf", f"fps=30,format=yuv420p,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,{subtitle_filter}",
            "-filter_complex", audio_filter,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            output_video
        ])
        
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            # 备用方案：不使用复杂音频滤镜，简化处理
            ffmpeg_cmd_simple = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", list_file,
                "-i", bgm_file,
                "-vf", f"fps=30,format=yuv420p,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-af", f"volume={BGM_VOLUME}",
                "-shortest",
                output_video
            ]
            result2 = subprocess.run(ffmpeg_cmd_simple, capture_output=True, text=True)
            
            if result2.returncode != 0:
                # 再备用：生成无字幕版本
                ffmpeg_cmd_nosub = [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0", "-i", list_file,
                    "-vf", "fps=30,format=yuv420p,scale=1080:1920",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                    "-an",  # 无音频
                    output_video
                ]
                subprocess.run(ffmpeg_cmd_nosub, capture_output=True, check=True)
        
        # Step 7: 如果上面生成了无字幕版本，单独添加字幕
        # 使用ffmpeg添加字幕滤镜
        if "subtitles" not in str(result.stdout) and os.path.exists(output_video):
            # 重新添加字幕
            temp_video = os.path.join(temp_dir, "video_no_sub.mp4")
            os.rename(output_video, temp_video)
            
            # 使用ASS字幕，样式已在文件中定义
            # 注意：需要转义路径中的特殊字符
            escaped_sub_path = subtitle_file.replace("'", "'\\''")
            ffmpeg_sub_cmd = [
                "ffmpeg", "-y",
                "-i", temp_video,
                "-vf", f"subtitles='{escaped_sub_path}'",
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-c:a", "copy",
                output_video
            ]
            sub_result = subprocess.run(ffmpeg_sub_cmd, capture_output=True, text=True)
            
            if sub_result.returncode != 0:
                # 字幕添加失败，使用原视频
                os.rename(temp_video, output_video)
        
        # Step 8: 上传最终视频到对象存储
        storage = S3SyncStorage(
            endpoint_url=os.getenv("COZE_BUCKET_ENDPOINT_URL"),
            access_key="",
            secret_key="",
            bucket_name=os.getenv("COZE_BUCKET_NAME"),
            region="cn-beijing"
        )
        
        with open(output_video, "rb") as f:
            video_data = f.read()
        
        video_key = storage.upload_file(
            file_content=video_data,
            file_name="stickman_story/final_video.mp4",
            content_type="video/mp4"
        )
        
        video_url = storage.generate_presigned_url(key=video_key, expire_time=86400)
        
    except Exception as e:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise Exception(f"视频合成失败: {e}")
    
    finally:
        # 清理临时目录
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    return VideoComposeOutput(base_video_url=video_url)


def _create_ass_subtitle(subtitle_file: str, sentences: List[str], frame_count: int) -> None:
    """创建ASS格式的字幕文件，支持丰富样式"""
    
    # ASS字幕文件头部
    ass_content = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,WenQuanYi Zen Hei,42,&H00FFFFFF,&H000000FF,&H00000000,&HA0000000,1,0,0,0,100,100,0,0,1,3,0,2,50,50,100,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    # 添加每个字幕条目
    for i, sentence in enumerate(sentences):
        start_time = i * IMAGE_DURATION
        end_time = (i + 1) * IMAGE_DURATION
        
        # 转换为ASS时间格式 H:MM:SS.CS
        start_h = int(start_time // 3600)
        start_m = int((start_time % 3600) // 60)
        start_s = int(start_time % 60)
        start_cs = int((start_time % 1) * 100)
        
        end_h = int(end_time // 3600)
        end_m = int((end_time % 3600) // 60)
        end_s = int(end_time % 60)
        end_cs = int((end_time % 1) * 100)
        
        start_str = f"{start_h}:{start_m:02d}:{start_s:02d}.{start_cs:02d}"
        end_str = f"{end_h}:{end_m:02d}:{end_s:02d}.{end_cs:02d}"
        
        # ASS对话行
        dialogue = f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{sentence}\n"
        ass_content += dialogue
    
    # 写入文件
    with open(subtitle_file, "w", encoding="utf-8") as f:
        f.write(ass_content)


def _generate_bgm(bgm_file: str, base_freq: int, duration: float) -> None:
    """生成柔和的背景音乐"""
    
    # 使用ffmpeg生成和弦风格的BGM
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency={base_freq}:duration={duration}",
        "-f", "lavfi",
        "-i", f"sine=frequency={int(base_freq*0.75)}:duration={duration}",
        "-f", "lavfi",
        "-i", f"sine=frequency={int(base_freq*1.5)}:duration={duration}",
        "-filter_complex", 
        "[0:a][1:a][2:a]amix=inputs=3:duration=longest[aout];[aout]volume=0.08",
        "-c:a", "libmp3lame", "-q:a", "4",
        bgm_file
    ]
    
    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        # 备用：单音符
        ffmpeg_cmd2 = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"sine=frequency={base_freq}:duration={duration}",
            "-af", "volume=0.1",
            "-c:a", "libmp3lame", "-q:a", "4",
            bgm_file
        ]
        result2 = subprocess.run(ffmpeg_cmd2, capture_output=True, text=True)
        
        if result2.returncode != 0:
            # 最后备用：静音
            ffmpeg_cmd3 = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"anullsrc=r=24000:cl=mono,duration={duration}",
                "-c:a", "libmp3lame", "-q:a", "4",
                bgm_file
            ]
            subprocess.run(ffmpeg_cmd3, capture_output=True, check=True)


def _get_bgm_frequency(story_type: str) -> int:
    """根据故事类型返回合适的背景音乐频率"""
    freq_mapping = {
        "励志": 440,   # A4音符
        "亲情": 392,   # G4音符
        "感悟": 330,   # E4音符
        "治愈": 262,   # C4音符
    }
    return freq_mapping.get(story_type, 392)