# 子图：单张图片生成循环
# 用于循环处理每个句子生成对应的漫画图片

import os
from typing import List
from langgraph.graph import StateGraph, END

from graphs.state import (
    GlobalState,
    SingleImageInput,
    SingleImageOutput
)
from graphs.nodes.single_image_gen_node import single_image_gen_node


# 子图状态定义（用于循环）
class ImageLoopState(GlobalState):
    """图片生成循环状态"""
    current_index: int = 0  # 当前处理的句子索引
    current_image_url: str = ""  # 当前生成的图片URL


def get_next_sentence(state: ImageLoopState) -> str:
    """
    title: 获取下一个待处理句子
    desc: 判断是否还有未处理的句子，返回继续或结束
    """
    sentences: List[str] = state.sentences
    current_index: int = state.current_index
    
    if current_index < len(sentences):
        return "继续生成"
    else:
        return "结束循环"


def prepare_single_image_input(state: ImageLoopState) -> SingleImageInput:
    """
    title: 准备单张图片生成输入
    desc: 从全局状态提取当前句子信息，构建节点输入
    """
    sentences: List[str] = state.sentences
    current_index: int = state.current_index
    
    return SingleImageInput(
        sentence=sentences[current_index],
        index=current_index,
        total_count=len(sentences)
    )


def update_loop_state(state: ImageLoopState, output: SingleImageOutput) -> ImageLoopState:
    """
    title: 更新循环状态
    desc: 将生成的图片URL添加到列表，推进索引
    """
    # 更新图片列表
    current_urls: List[str] = state.image_urls
    current_urls.append(output.image_url)
    
    return ImageLoopState(
        image_urls=current_urls,
        current_index=state.current_index + 1
    )


# 构建子图
def build_image_gen_subgraph() -> StateGraph:
    """构建图片生成循环子图"""
    
    builder = StateGraph(
        ImageLoopState,
        input_schema=SingleImageInput,
        output_schema=SingleImageOutput
    )
    
    # 添加节点
    builder.add_node("single_image_gen", single_image_gen_node)
    
    # 设置入口点
    builder.set_entry_point("single_image_gen")
    
    # 添加条件边（循环判断）
    builder.add_conditional_edges(
        source="single_image_gen",
        path=get_next_sentence,
        path_map={
            "继续生成": "single_image_gen",  # 继续循环
            "结束循环": END  # 结束
        }
    )
    
    return builder.compile()


# 导出子图实例
image_gen_subgraph = build_image_gen_subgraph()