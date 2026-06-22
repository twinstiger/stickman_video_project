# 节点模块初始化
# 火柴人剧情漫画故事视频生成工作流

from graphs.nodes.split_story_node import split_story_node
from graphs.nodes.generate_images_node import generate_images_node
from graphs.nodes.video_compose_node import video_compose_node
from graphs.nodes.audio_embed_node import audio_embed_node
from graphs.nodes.cover_export_node import cover_export_node
from graphs.nodes.single_image_gen_node import single_image_gen_node


__all__ = [
    "split_story_node",
    "generate_images_node",
    "video_compose_node",
    "audio_embed_node",
    "cover_export_node",
    "single_image_gen_node",
]