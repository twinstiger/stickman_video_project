# 单张图片生成节点（子图使用）
# 为单个句子生成对应的火柴人漫画分镜图

import os
from typing import List
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from coze_coding_dev_sdk import ImageGenerationClient

from graphs.state import SingleImageInput, SingleImageOutput


# 固定正向绘图提示词（全局通用）
POSITIVE_PROMPT_TEMPLATE = """9:16竖屏抖音短视频分镜，黑白线条火柴人漫画，完整叙事漫画分镜，画面自带完整剧情场景与环境道具，人物互动自然，线条干净流畅，极简手绘风格，浅灰色纯色背景，无多余装饰，构图完整有故事感，高清画质，无文字，无水印，无五官人脸，无彩色元素，氛围感治愈叙事，贴合以下剧情内容作画：{sentence}"""

# 固定负面提示词（强制避雷）
NEGATIVE_PROMPT = "极简单线无场景火柴人，空白背景，彩色画面，人物五官，人脸，卡通画风，3D画风，水印，画面自带文字，杂乱元素，夸张特效，低清模糊，多余装饰，写实人物"


def single_image_gen_node(
    state: SingleImageInput,
    config: RunnableConfig,
    runtime: Runtime[Context]
) -> SingleImageOutput:
    """
    title: 单张漫画分镜生成
    desc: 根据单句台词内容生成对应的火柴人漫画分镜图，9:16竖屏，黑白手绘风格
    integrations: 图片生成
    """
    ctx = runtime.context
    
    # 构建完整提示词
    sentence = state.sentence
    positive_prompt = POSITIVE_PROMPT_TEMPLATE.format(sentence=sentence)
    
    # 添加序列信息提示，保持画风一致和剧情连贯
    sequence_hint = f"\n这是故事的第{state.index + 1}帧画面，共{state.total_count}帧。保持前后画面风格统一、人物形象一致。"
    full_prompt = positive_prompt + sequence_hint
    
    # 初始化图片生成客户端
    client = ImageGenerationClient(ctx=ctx)
    
    # 生成图片（9:16竖屏，使用2K尺寸的竖屏比例）
    # 9:16竖屏：1080x1920，使用自定义尺寸
    response = client.generate(
        prompt=full_prompt,
        size="1080x1920",  # 9:16竖屏比例
        watermark=False,  # 无水印
        model="doubao-seedream-5-0-260128"
    )
    
    if response.success and response.image_urls:
        image_url = response.image_urls[0]
    else:
        # 生成失败时抛出异常
        error_msgs = response.error_messages if hasattr(response, 'error_messages') else ["图片生成失败"]
        raise Exception(f"图片生成失败: {', '.join(error_msgs)}")
    
    return SingleImageOutput(image_url=image_url)