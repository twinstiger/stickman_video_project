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
    
    video_url = state.base_video_url
    image_urls: List[str] = state.image_urls
    story_title = state.story_title
    
    # 初始化客户端
    img_client = ImageGenerationClient(ctx=ctx)
    storage = S3SyncStorage(
        endpoint_url=os.getenv("COZE_BUCKET_ENDPOINT_URL"),
        access_key="",
        secret_key="",
        bucket_name=os.getenv("COZE_BUCKET_NAME"),
        region="cn-beijing"
    )
    
    # Step 1: 选择高潮画面作为封面基底
    # 选择故事中间偏后的画面（通常是高潮部分）
    if image_urls:
        climax_index = len(image_urls) // 2 + len(image_urls) // 4
        climax_index = min(climax_index, len(image_urls) - 1)
        climax_image_url = image_urls[climax_index]
    else:
        climax_image_url = ""
    
    # Step 2: 生成带标题的封面图片
    cover_image_url = climax_image_url
    
    try:
        # 使用高潮画面作为参考，生成带标题的封面
        safe_title = story_title.replace('"', '').replace("'", "")
        cover_prompt = f"""黑白线条火柴人漫画风格封面图，9:16竖屏，画面底部添加加粗标题文字"{safe_title}"，白色粗体配黑色描边，高清画质"""
        
        cover_response = img_client.generate(
            prompt=cover_prompt,
            image=climax_image_url,
            size="1080x1920",
            watermark=False,
            model="doubao-seedream-5-0-260128"
        )
        
        if cover_response.success and cover_response.image_urls:
            cover_image_url = cover_response.image_urls[0]
            
    except Exception:
        # 使用高潮画面作为备选封面
        pass
    
    # Step 3: 上传封面到对象存储
    try:
        cover_data = requests.get(cover_image_url, timeout=30).content
        
        # 清理文件名中的特殊字符
        safe_file_title = "".join(c if c.isalnum() or c in '_-' else '_' for c in story_title)
        cover_key = storage.upload_file(
            file_content=cover_data,
            file_name=f"stickman_story/cover_{safe_file_title}.png",
            content_type="image/png"
        )
        
        cover_image_url = storage.generate_presigned_url(key=cover_key, expire_time=86400)
        
    except Exception:
        # 保持原封面URL
        pass
    
    # Step 4: 最终视频直接使用（已包含字幕和音频）
    final_video_url = video_url
    
    return CoverExportOutput(
        final_video_url=final_video_url,
        cover_image_url=cover_image_url
    )