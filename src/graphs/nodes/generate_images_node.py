# 图片生成调用节点（主图节点）
# 调用子图循环生成所有漫画图片

import os
import asyncio
from typing import List
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from coze_coding_dev_sdk import ImageGenerationClient

from graphs.state import GenerateImagesInput, GenerateImagesOutput
from graphs.loop_graph import image_gen_subgraph


# 固定正向绘图提示词模板
POSITIVE_PROMPT_TEMPLATE = """9:16竖屏抖音短视频分镜，黑白线条火柴人漫画，完整叙事漫画分镜，
画面自带完整剧情场景与环境道具，人物互动自然，线条干净流畅，极简手绘风格，
浅灰色纯色背景，无多余装饰，构图完整有故事感，高清画质，无文字，无水印，
无五官人脸，无彩色元素，氛围感治愈叙事，贴合以下剧情内容作画：{sentence}"""


def generate_images_node(
    state: GenerateImagesInput,
    config: RunnableConfig,
    runtime: Runtime[Context]
) -> GenerateImagesOutput:
    """
    title: 漫画图片批量生成
    desc: 循环处理每句台词，生成对应的火柴人漫画分镜图，保持画风一致
    integrations: 图片生成
    """
    ctx = runtime.context
    
    sentences: List[str] = state.sentences
    total_count = len(sentences)
    
    if not sentences:
        raise Exception("没有可用的台词句子进行图片生成")
    
    # 初始化图片生成客户端
    client = ImageGenerationClient(ctx=ctx)
    
    # 并行生成所有图片（使用async提高效率）
    image_urls: List[str] = []
    
    # 由于LangGraph节点是同步函数，我们使用asyncio.run包装
    async def generate_all_images():
        tasks = []
        for i, sentence in enumerate(sentences):
            prompt = POSITIVE_PROMPT_TEMPLATE.format(sentence=sentence)
            sequence_hint = f"\n这是故事的第{i + 1}帧画面，共{total_count}帧。保持前后画面风格统一、人物形象一致。"
            full_prompt = prompt + sequence_hint
            
            tasks.append(client.generate_async(
                prompt=full_prompt,
                size="1080x1920",  # 9:16竖屏
                watermark=False,
                model="doubao-seedream-5-0-260128"
            ))
        
        # 使用Semaphore控制并发数量（避免API限流）
        semaphore = asyncio.Semaphore(3)  # 最大并发3个
        
        async def generate_with_limit(task):
            async with semaphore:
                return await task
        
        results = await asyncio.gather(*[generate_with_limit(t) for t in tasks])
        return results
    
    # 执行并行生成
    results = asyncio.run(generate_all_images())
    
    # 收集结果
    for i, response in enumerate(results):
        if response.success and response.image_urls:
            image_urls.append(response.image_urls[0])
        else:
            # 生成失败，记录错误
            error_msgs = response.error_messages if hasattr(response, 'error_messages') else ["图片生成失败"]
            raise Exception(f"第{i + 1}张图片生成失败: {', '.join(error_msgs)}")
    
    return GenerateImagesOutput(image_urls=image_urls)