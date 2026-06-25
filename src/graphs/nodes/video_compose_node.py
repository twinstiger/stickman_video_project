# 视频合成节点（动态时长版本）
# 根据TTS朗读时长动态设置每张图片的显示时间

import os
import json
import logging
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

# 初始化logger
logger = logging.getLogger(__name__)

# 最小图片显示时间（秒）- 确保即使音频很短，画面也有足够展示时间
MIN_IMAGE_DURATION = 2.5

# BGM音量
BGM_VOLUME = 0.15

# 字幕样式参数
FONT_FILE = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
FONT_SIZE = 42
FONT_COLOR = "white"
BORDER_COLOR = "black"
BORDER_WIDTH = 3
BACKGROUND_COLOR = "black@0.4"


def video_compose_node(
    state: VideoComposeInput,
    config: RunnableConfig,
    runtime: Runtime[Context]
) -> VideoComposeOutput:
    """
    title: 视频合成（动态时长版）
    desc: 根据TTS朗读时长动态设置画面显示时间，朗读完成后再切换画面
    integrations: 对象存储、TTS
    """
    ctx = runtime.context
    
    image_urls: List[str] = state.image_urls
    sentences: List[str] = state.sentences
    story_type: str = state.story_type if hasattr(state, 'story_type') else "励志"
    story_text: str = state.story_text if hasattr(state, 'story_text') else ""
    enable_narration: bool = state.enable_narration if hasattr(state, 'enable_narration') else False
    voice_type: str = state.voice_type if hasattr(state, 'voice_type') else "励志女声"
    
    if not image_urls:
        raise Exception("没有可用的图片进行视频合成")
    
    temp_dir = tempfile.mkdtemp(prefix="stickman_dynamic_")
    
    try:
        # Step 1: 下载所有图片
        frame_paths: List[str] = []
        for i, url in enumerate(image_urls):
            img_path = os.path.join(temp_dir, f"frame_{i:03d}.png")
            resp = requests.get(url, timeout=30)
            with open(img_path, "wb") as f:
                f.write(resp.content)
            frame_paths.append(img_path)
        logger.info(f"Downloaded {len(frame_paths)} images")
        
        # Step 2: 如果启用旁白，先生成所有TTS音频并获取时长
        narration_segments: List[str] = []
        segment_durations: List[float] = []  # 每个片段的实际时长
        total_duration = 0.0
        
        if enable_narration and sentences:
            tts_client = TTSClient(ctx=ctx)
            
            voice_mapping = {
                "励志女声": "zh_female_jitangnv_saturn_bigtts",
                "温柔女声": "zh_female_santongyongns_saturn_bigtts",
                "甜美女声": "zh_female_meilinvyou_saturn_bigtts",
                "通用女声": "zh_female_xiaohe_uranus_bigtts",
            }
            speaker = voice_mapping.get(voice_type, "zh_female_jitangnv_saturn_bigtts")
            logger.info(f"Selected voice: {voice_type} -> {speaker}, speech_rate=+15 (1.5x)")
            
            narration_count = min(len(sentences), len(frame_paths))
            logger.info(f"Narration count: {narration_count}")
            
            # 先生成所有TTS音频
            for i in range(narration_count):
                sentence = sentences[i] if i < len(sentences) else ""
                if not sentence.strip():
                    narration_segments.append(None)
                    segment_durations.append(MIN_IMAGE_DURATION)
                    continue
                    
                seg_file = os.path.join(temp_dir, f"narration_seg_{i:03d}.mp3")
                try:
                    narration_url, audio_size = tts_client.synthesize(
                        uid=f"stickman_narrator_{i}",
                        text=sentence,
                        speaker=speaker,
                        audio_format="mp3",
                        sample_rate=24000,
                        speech_rate=15,  # 1.5倍语速（加快）
                        loudness_rate=20
                    )
                    logger.info(f"TTS segment {i}: url={narration_url}, size={audio_size}")
                    resp = requests.get(narration_url, timeout=30)
                    if resp.status_code == 200 and len(resp.content) > 0:
                        with open(seg_file, "wb") as f:
                            f.write(resp.content)
                        narration_segments.append(seg_file)
                        # 获取音频实际时长
                        duration = _get_audio_duration(seg_file)
                        segment_durations.append(duration)
                        logger.info(f"Segment {i} duration: {duration:.2f}s (sentence: {len(sentence)} chars)")
                    else:
                        narration_segments.append(None)
                        segment_durations.append(MIN_IMAGE_DURATION)
                except Exception as e:
                    logger.warning(f"TTS segment {i} failed: {e}")
                    narration_segments.append(None)
                    segment_durations.append(MIN_IMAGE_DURATION)
        else:
            # 没有旁白，使用固定时长
            segment_durations = [MIN_IMAGE_DURATION] * len(frame_paths)
        
        # Step 3: 计算每张图片的显示时间（朗读时长，最小MIN_IMAGE_DURATION）
        frame_durations: List[float] = []
        cumulative_times: List[float] = [0.0]  # 累积时间，用于字幕和旁白定位
        
        for i in range(len(frame_paths)):
            # 图片时长 = max(最小时长, 对应音频时长)
            duration = segment_durations[i] if i < len(segment_durations) else MIN_IMAGE_DURATION
            frame_duration = max(MIN_IMAGE_DURATION, duration)
            frame_durations.append(frame_duration)
            cumulative_times.append(cumulative_times[-1] + frame_duration)
        
        total_duration = cumulative_times[-1]
        logger.info(f"Frame durations: {frame_durations}")
        logger.info(f"Cumulative times: {cumulative_times}")
        logger.info(f"Total video duration: {total_duration:.2f}s")
        
        # Step 4: 创建动态时长的图片列表文件
        list_file = os.path.join(temp_dir, "frames.txt")
        with open(list_file, "w") as f:
            for i, path in enumerate(frame_paths):
                f.write(f"file '{path}'\n")
                f.write(f"duration {frame_durations[i]}\n")
            if frame_paths:
                f.write(f"file '{frame_paths[-1]}'\n")  # ffmpeg要求最后一帧要重复
        
        # Step 5: 创建字幕（使用动态时间）
        subtitle_file = os.path.join(temp_dir, "subtitles.ass")
        _create_dynamic_ass_subtitle(subtitle_file, sentences, cumulative_times, len(frame_paths))
        
        # Step 6: 生成BGM（根据视频总时长）
        bgm_file = os.path.join(temp_dir, "bgm.mp3")
        bgm_freq = _get_bgm_frequency(story_type)
        _generate_bgm(bgm_file, bgm_freq, total_duration)
        logger.info(f"Generated BGM: {total_duration:.2f}s")
        
        # Step 7: 合成旁白音频（不截断，按实际时长放置）
        narration_file = None
        if enable_narration and any(s is not None for s in narration_segments):
            narration_file = os.path.join(temp_dir, "narration.mp3")
            valid_segments = [(i, s) for i, s in enumerate(narration_segments) if s is not None]
            logger.info(f"Processing {len(valid_segments)} valid narration segments")
            
            # 创建空白底轨
            silence_file = os.path.join(temp_dir, "silence.mp3")
            _generate_silence(silence_file, total_duration)
            
            # 构建ffmpeg命令（不使用atrim，保留完整音频）
            inputs = ["-i", silence_file]
            filter_parts = []
            
            for idx, (i, seg_file) in enumerate(valid_segments):
                inputs.extend(["-i", seg_file])
                # 延迟到对应画面开始时间（不截断！）
                delay_ms = int(cumulative_times[i] * 1000)
                filter_parts.append(f"[{idx+1}:a]adelay={delay_ms}|{delay_ms}[seg{idx}]")
                logger.info(f"Segment {i}: delay={delay_ms}ms (no trim, keep full audio)")
            
            if len(valid_segments) > 0:
                mix_inputs = "".join([f"[seg{i}]" for i in range(len(valid_segments))])
                filter_parts.append(f"[0:a]{mix_inputs}amix=inputs={len(valid_segments)+1}:duration=first:dropout_transition=0:normalize=0[narration_out]")
                filter_complex_narration = ";".join(filter_parts)
                
                ffmpeg_merge_cmd = [
                    "ffmpeg", "-y",
                    *inputs,
                    "-filter_complex", filter_complex_narration,
                    "-map", "[narration_out]",
                    "-c:a", "libmp3lame", "-q:a", "4",
                    narration_file
                ]
                logger.info(f"FFmpeg narration merge: {filter_complex_narration}")
                result = subprocess.run(ffmpeg_merge_cmd, capture_output=True, text=True, timeout=120)
                if result.returncode != 0:
                    logger.warning(f"Narration merge failed: {result.stderr}")
                    narration_file = None
                else:
                    logger.info(f"Narration merged successfully: {narration_file}")
        
        # Step 8: 合成最终视频（视频+字幕+音频）
        final_video_path = os.path.join(temp_dir, "final_video.mp4")
        
        # 确定音频输入
        audio_inputs = []
        audio_filter = ""
        
        if narration_file:
            # 有旁白：BGM + 旁白
            audio_inputs = ["-i", bgm_file, "-i", narration_file]
            # 输入索引：0=base_video(无音频), 1=bgm, 2=narration
            # BGM音量15%，旁白音量90%
            audio_filter = f"[1:a]volume={BGM_VOLUME}[bgm];[2:a]volume=0.9[narration];[bgm][narration]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
        else:
            # 无旁白：只有BGM
            audio_inputs = ["-i", bgm_file]
            # 输入索引：0=base_video(无音频), 1=bgm
            audio_filter = f"[1:a]volume={BGM_VOLUME}[aout]"
        
        # 使用filter_complex处理视频滤镜（字幕）和音频混合
        # 视频输入是concat demuxer，所以需要先通过concat读取
        # 先生成无字幕视频，再添加字幕
        
        base_video = os.path.join(temp_dir, "base_video.mp4")
        
        # Step 8a: 先合成基础视频（图片序列 → 视频）
        ffmpeg_video_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", list_file,
            "-vf", "fps=30,format=yuv420p",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-an",  # 无音频
            base_video
        ]
        logger.info("Creating base video from images...")
        result = subprocess.run(ffmpeg_video_cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.error(f"Base video creation failed: {result.stderr}")
            raise Exception(f"基础视频合成失败: {result.stderr}")
        
        # Step 8b: 添加字幕和音频
        final_inputs = ["-i", base_video] + audio_inputs
        
        # 构建filter_complex：字幕 + 音频
        # 注意：字幕滤镜中的单引号需要转义
        subtitle_path_escaped = subtitle_file.replace("'", "'\\''")
        video_filter = f"subtitles='{subtitle_path_escaped}':force_style='FontName=WenQuanYi Zen Hei,FontSize={FONT_SIZE},PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline={BORDER_WIDTH},BackColour=&HA0000000,MarginV=20'"
        
        filter_complex_parts = [f"[0:v]{video_filter}[vout]"]
        if audio_filter:
            filter_complex_parts.append(audio_filter)
        filter_complex = ";".join(filter_complex_parts)
        
        ffmpeg_final_cmd = [
            "ffmpeg", "-y",
            *final_inputs,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[aout]" if audio_filter else "0:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            final_video_path
        ]
        
        logger.info(f"Final video command: filter_complex={filter_complex}")
        result = subprocess.run(ffmpeg_final_cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            logger.error(f"Final video failed: {result.stderr}")
            # 备用方案：只添加音频，不添加字幕
            logger.info("Trying fallback: video + audio only")
            ffmpeg_fallback_cmd = [
                "ffmpeg", "-y",
                "-i", base_video,
                *audio_inputs,
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                final_video_path
            ]
            if narration_file:
                ffmpeg_fallback_cmd.extend([
                    "-filter_complex", audio_filter,
                    "-map", "0:v", "-map", "[aout]"
                ])
            result = subprocess.run(ffmpeg_fallback_cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                raise Exception(f"视频合成失败: {result.stderr}")
        
        # Step 9: 上传视频到对象存储
        storage = S3SyncStorage()
        
        # 读取视频文件内容并上传
        with open(final_video_path, "rb") as f:
            video_content = f.read()
        
        video_key = storage.upload_file(
            file_content=video_content,
            file_name=f"stickman_story/final_video_{os.urandom(4).hex()}.mp4",
            content_type="video/mp4"
        )
        
        video_url = storage.generate_presigned_url(key=video_key, expire_time=86400)
        logger.info(f"Video uploaded: {video_url}")
        
        return VideoComposeOutput(
            base_video_url=video_url,
            sentences=sentences
        )
        
    except Exception as e:
        logger.error(f"Video compose failed: {e}")
        raise Exception(f"视频合成失败: {e}")


def _get_audio_duration(audio_file: str) -> float:
    """使用ffprobe获取音频时长"""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_file
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
        return MIN_IMAGE_DURATION
    except Exception as e:
        logger.warning(f"Failed to get audio duration: {e}")
        return MIN_IMAGE_DURATION


def _create_dynamic_ass_subtitle(subtitle_file: str, sentences: List[str], cumulative_times: List[float], frame_count: int):
    """创建动态时间的ASS字幕文件"""
    with open(subtitle_file, "w", encoding="utf-8") as f:
        f.write("[Script Info]\n")
        f.write("ScriptType: v4.00+\n")
        f.write("PlayResX: 1080\n")
        f.write("PlayResY: 1920\n")
        f.write("ScaledBorderAndShadow: yes\n")
        f.write("\n")
        f.write("[V4+ Styles]\n")
        f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
        f.write(f"Style: Default,WenQuanYi Zen Hei,{FONT_SIZE},&H00FFFFFF,&H000000FF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,1,{BORDER_WIDTH},0,8,50,50,50,1\n")
        f.write("\n")
        f.write("[Events]\n")
        f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        
        # 限制字幕数量与图片数量一致
        subtitle_count = min(len(sentences), frame_count)
        
        for i in range(subtitle_count):
            start_time = cumulative_times[i]
            end_time = cumulative_times[i + 1] if i + 1 < len(cumulative_times) else cumulative_times[i] + MIN_IMAGE_DURATION
            
            # ASS时间格式: H:MM:SS.cc
            start_h = int(start_time // 3600)
            start_m = int((start_time % 3600) // 60)
            start_s = start_time % 60
            start_ass = f"{start_h}:{start_m:02d}:{start_s:05.2f}"
            
            end_h = int(end_time // 3600)
            end_m = int((end_time % 3600) // 60)
            end_s = end_time % 60
            end_ass = f"{end_h}:{end_m:02d}:{end_s:05.2f}"
            
            sentence = sentences[i] if i < len(sentences) else ""
            # 自动换行：超过15个字符换行
            text = _wrap_subtitle_text(sentence, max_chars=15)
            
            f.write(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{text}\n")


def _wrap_subtitle_text(text: str, max_chars: int = 15) -> str:
    """将字幕文本自动换行，每行不超过max_chars个字符"""
    if len(text) <= max_chars:
        return text.replace("\n", "\\N")
    
    # 智能换行：优先在标点符号处换行
    lines = []
    current_line = ""
    punctuation = "，。！？、；：""''（）【】"
    
    for char in text:
        current_line += char
        # 如果达到最大长度且遇到标点，换行
        if len(current_line) >= max_chars and char in punctuation:
            lines.append(current_line)
            current_line = ""
        # 如果超过最大长度1.5倍，强制换行
        elif len(current_line) >= max_chars * 1.5:
            lines.append(current_line)
            current_line = ""
    
    if current_line:
        lines.append(current_line)
    
    # 用ASS换行符连接
    return "\\N".join(lines)


def _get_bgm_frequency(story_type: str) -> int:
    """根据故事类型返回BGM基础频率"""
    type_freq = {
        "励志": 440,    # A4音符，振奋人心
        "亲情": 392,    # G4音符，温暖柔和
        "感悟": 330,    # E4音符，深沉思考
        "治愈": 262,    # C4音符，舒缓平静
    }
    return type_freq.get(story_type, 330)


def _generate_bgm(output_file: str, base_freq: int, duration: float):
    """生成和弦风格BGM（三个频率叠加）"""
    # 和弦构成：主音 + 低音（主音/2） + 高音（主音*1.5）
    freq1 = base_freq       # 主音
    freq2 = base_freq // 2  # 低音（八度下）
    freq3 = int(base_freq * 1.5)  # 高音（五度上）
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r=24000:cl=mono",
        "-f", "lavfi",
        "-i", f"sine=frequency={freq1}:duration={duration}",
        "-f", "lavfi",
        "-i", f"sine=frequency={freq2}:duration={duration}",
        "-f", "lavfi",
        "-i", f"sine=frequency={freq3}:duration={duration}",
        "-filter_complex",
        f"[1:a][2:a][3:a]amix=inputs=3:duration=first:normalize=0[audio];[audio]volume=0.05[out]",
        "-map", "[out]",
        "-t", str(duration),
        "-c:a", "libmp3lame", "-q:a", "4",
        output_file
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def _generate_silence(output_file: str, duration: float):
    """生成空白音频底轨"""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r=24000:cl=mono",
        "-t", str(duration),
        "-c:a", "libmp3lame", "-q:a", "4",
        output_file
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=60)