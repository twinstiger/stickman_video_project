# 单张图片生成节点（子图使用）
# 为单个句子生成对应的火柴人漫画分镜图

import os
from typing import List
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from coze_coding_dev_sdk import ImageGenerationClient

from graphs.state import SingleImageInput, SingleImageOutput


# 固定正向绘图提示词（全局通用）- 丰富的画面细节
POSITIVE_PROMPT_TEMPLATE = """9:16竖屏抖音短视频分镜，黑白线条火柴人漫画风格，精细手绘线条艺术，专业漫画分镜构图。

画面要求：
- 丰富的场景细节：室内场景包含家具、摆件、墙面纹理、窗户光影；室外场景包含建筑、树木、道路、天空云层
- 多层次构图：前景人物、中景互动、远景背景，层次分明有空间感
- 环境道具精细：桌椅、茶具、书架、灯具、门窗、栏杆等细节丰富
- 光影效果：柔和的明暗过渡，阴影层次自然，营造氛围感
- 人物动态生动：火柴人姿态自然，动作夸张有张力，肢体表达情感
- 背景元素：透视正确的室内空间、街道场景、自然风景等
- 线条技法：粗细变化的笔触，重点突出轮廓，细节用细线点缀
- 空间透视：正确的透视关系，远近物体大小比例协调

风格：黑白漫画，手绘质感，治愈叙事氛围，画面故事感强烈。
内容：贴合以下剧情内容作画 - {sentence}"""

# 固定负面提示词（强制避雷）
NEGATIVE_PROMPT = """极简单线火柴人，空白白色背景，单一场景无细节，彩色画面，人物五官细节，真人脸，卡通萌系画风，3D渲染，照片写实，水印，画面自带文字标题，杂乱无章，夸张特效滤镜，低清模糊噪点，多余装饰花纹，写实人物照片，动漫美型风格，过度阴影黑暗"""


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