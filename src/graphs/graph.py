# 主图编排：火柴人剧情漫画故事视频生成工作流
# 输入完整故事文本 -> 输出MP4视频

from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from graphs.state import (
    GlobalState,
    GraphInput,
    GraphOutput,
    SplitStoryInput,
    SplitStoryOutput,
    GenerateImagesInput,
    GenerateImagesOutput,
    VideoComposeInput,
    VideoComposeOutput,
    CoverExportInput,
    CoverExportOutput
)

# 导入节点函数
from graphs.nodes.split_story_node import split_story_node
from graphs.nodes.generate_images_node import generate_images_node
from graphs.nodes.video_compose_node import video_compose_node
from graphs.nodes.cover_export_node import cover_export_node


# ==================== 主图构建 ====================
def build_main_graph() -> StateGraph:
    """构建主工作流图"""
    
    builder = StateGraph(
        GlobalState,
        input_schema=GraphInput,
        output_schema=GraphOutput
    )
    
    # 添加节点
    builder.add_node(
        "split_story",
        split_story_node,
        metadata={
            "type": "agent",
            "llm_cfg": "config/split_story_llm_cfg.json"
        }
    )
    
    builder.add_node(
        "generate_images",
        generate_images_node
    )
    
    builder.add_node(
        "video_compose",
        video_compose_node
    )
    
    builder.add_node(
        "cover_export",
        cover_export_node
    )
    
    # 设置入口点
    builder.set_entry_point("split_story")
    
    # 线性流程
    builder.add_edge("split_story", "generate_images")
    builder.add_edge("generate_images", "video_compose")
    builder.add_edge("video_compose", "cover_export")
    builder.add_edge("cover_export", END)
    
    return builder.compile()


# 导出主图实例
main_graph = build_main_graph()