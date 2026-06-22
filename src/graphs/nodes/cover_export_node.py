# 封面生成&导出节点
# 生成视频封面，导出最终视频

import os
import requests
import tempfile
from typing import List
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from coze_coding_dev_sdk import ImageGenerationClient
from coze_coding_dev_sdk.s3 import S3SyncStorage
from coze_coding_dev_sdk.video_edit import VideoEditClient

from graphs.state import CoverExportInput, CoverExportOutput


def cover_export_node(
    state: CoverExportInput,
    config: RunnableConfig,
    runtime: Runtime[Context]
) -> CoverExportOutput:
    """
    title: 封面生成&视频导出
    desc: 自动截取故事高潮画面作为封面，添加加粗故事标题，导出最终MP4视频
    integrations: 图片生成, 对象存储
    """
    ctx = runtime.context
    
    video_url = state.video_with_audio_url
    image_urls: List[str] = state.image_urls
    story_title = state.story_title
    
    # 初始化客户端
    img_client = ImageGenerationClient(ctx=ctx)
    storage = S3SyncStorage(
        endpoint_url=os.getenv("COZE_BUCKET_ENDPOINT_URL"),
        bucket_name=os.getenv("COZE_BUCKET_NAME"),
        region="cn-beijing"
    )
    video_client = VideoEditClient(ctx=ctx)
    
    # Step 1: 选择高潮画面作为封面基底
    # 选择故事中间偏后的画面（通常是高潮部分）
    climax_index = len(image_urls) // 2 + len(image_urls) // 4  # 约3/4位置
    climax_index = min(climax_index, len(image_urls) - 1)
    climax_image_url = image_urls[climax_index] if image_urls else image_urls[0] if image_urls else ""
    
    # Step 2: 生成带标题的封面图片
    try:
        # 使用高潮画面作为参考，生成带标题的封面
        cover_prompt = f"""9:16竖屏抖音视频封面，黑白线条火柴人漫画风格，画面中央有故事高潮场景，
        底部添加大号加粗故事标题文字："{story_title}"，标题使用白色粗体字配黑色描边，
        整体构图美观，适合作为视频封面，高清画质"""
        
        cover_response = img_client.generate(
            prompt=cover_prompt,
            image=climax_image_url,  # 参考高潮画面
            size="1080x1920",  # 9:16竖屏
            watermark=False,
            model="doubao-seedream-5-0-260128"
        )
        
        if cover_response.success and cover_response.image_urls:
            cover_image_url = cover_response.image_urls[0]
        else:
            # 封面生成失败，使用高潮画面作为封面
            cover_image_url = climax_image_url
            
    except Exception as e:
        # 使用高潮画面作为备选封面
        cover_image_url = climax_image_url
    
    # Step 3: 最终视频已经是带音频的，直接作为导出结果
    # 如果需要进一步处理（如添加封面帧），可以进行额外合成
    final_video_url = video_url
    
    # Step 4: 上传封面到对象存储（持久化）
    try:
        # 下载封面图片
        cover_data = requests.get(cover_image_url, timeout=30).content
        
        cover_key = storage.upload_file(
            file_content=cover_data,
            file_name=f"stickman_story/cover_{story_title}.png",
            content_type="image/png"
        )
        
        cover_image_url = storage.generate_presigned_url(key=cover_key, expire_time=86400)
        
    except Exception as e:
        # 保持原封面URL
        pass
    
    return CoverExportOutput(
        final_video_url=final_video_url,
        cover_image_url=cover_image_url
    )


def _add_cover_frame_to_video(
    video_client: VideoEditClient,
    video_url: str,
    cover_url: str,
    story_title: str,
    temp_dir: str,
    storage: S3SyncStorage
) -> str:
    """将封面作为视频首帧（可选增强）"""
    
    import subprocess
    
    # 下载封面
    cover_path = os.path.join(temp_dir, "cover.png")
    resp = requests.get(cover_url, timeout=30)
    with open(cover_path, "wb") as f:
        f.write(resp.content)
    
    # 将封面转为1秒视频片段
    cover_video_path = os.path.join(temp_dir, "cover_segment.mp4")
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", cover_path,
        "-t", "1",  # 1秒时长
        "-vf", "fps=30,format=yuv420p",
        "-c:v", "libx264",
        "-s", "1080x1920",
        cover_video_path
    ]
    subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
    
    # 下载原视频
    original_video_path = os.path.join(temp_dir, "original.mp4")
    resp = requests.get(video_url, timeout=60)
    with open(original_video_path, "wb") as f:
        f.write(resp.content)
    
    # 拼接封面和原视频
    final_video_path = os.path.join(temp_dir, "final_with_cover.mp4")
    concat_file = os.path.join(temp_dir, "concat.txt")
    with open(concat_file, "w") as f:
        f.write(f"file '{cover_video_path}'\n")
        f.write(f"file '{original_video_path}'\n")
    
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_file,
        "-c:v", "libx264", "-c:a", "copy",
        final_video_path
    ]
    subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
    
    # 上传最终视频
    with open(final_video_path, "rb") as f:
        video_data = f.read()
    
    video_key = storage.upload_file(
        file_content=video_data,
        file_name=f"stickman_story/final_{story_title}.mp4",
        content_type="video/mp4"
    )
    
    return storage.generate_presigned_url(key=video_key, expire_time=86400)