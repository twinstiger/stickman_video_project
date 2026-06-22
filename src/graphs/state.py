# 工作流状态定义
# 火柴人剧情漫画故事视频生成工作流

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# ==================== 全局状态 ====================
class GlobalState(BaseModel):
    """工作流全局状态"""
    # 原始输入
    story_text: str = Field(default="", description="用户输入的完整故事文本")
    enable_narration: bool = Field(default=False, description="是否启用AI旁白朗读")
    
    # 分句结果
    sentences: List[str] = Field(default=[], description="智能拆分后的台词句子列表")
    story_type: str = Field(default="", description="故事类型：励志/亲情/感悟/治愈")
    story_title: str = Field(default="", description="故事标题")
    
    # 图片生成结果
    image_urls: List[str] = Field(default=[], description="生成的漫画图片URL列表")
    
    # 视频合成结果
    base_video_url: str = Field(default="", description="无音频的基础视频URL")
    
    # 音频嵌入结果
    video_with_audio_url: str = Field(default="", description="带音频的完整视频URL")
    
    # 最终输出
    final_video_url: str = Field(default="", description="最终导出的MP4视频URL")
    cover_image_url: str = Field(default="", description="视频封面图片URL")


# ==================== 图输入输出 ====================
class GraphInput(BaseModel):
    """工作流输入参数"""
    story_text: str = Field(..., description="完整的故事文本，支持励志、亲情、感悟类故事")
    enable_narration: bool = Field(default=False, description="是否启用AI旁白朗读（可选功能）")


class GraphOutput(BaseModel):
    """工作流输出结果"""
    final_video_url: str = Field(..., description="最终生成的完整MP4视频URL，可直接上传抖音")
    cover_image_url: str = Field(..., description="视频封面图片URL，包含故事标题")


# ==================== 节点1：智能语义分句 ====================
class SplitStoryInput(BaseModel):
    """智能分句节点输入"""
    story_text: str = Field(..., description="完整的原始故事文本")


class SplitStoryOutput(BaseModel):
    """智能分句节点输出"""
    sentences: List[str] = Field(..., description="智能拆分后的台词句子列表，每句对应一个画面")
    story_type: str = Field(..., description="识别的故事类型：励志/亲情/感悟/治愈")
    story_title: str = Field(..., description="提取或生成的故事标题")


# ==================== 节点2：循环图片生成 ====================
class GenerateImagesInput(BaseModel):
    """图片生成节点输入"""
    sentences: List[str] = Field(..., description="需要生成画面的台词句子列表")


class GenerateImagesOutput(BaseModel):
    """图片生成节点输出"""
    image_urls: List[str] = Field(..., description="生成的火柴人漫画图片URL列表")


# ==================== 子图：单张图片生成 ====================
class SingleImageInput(BaseModel):
    """单张图片生成输入"""
    sentence: str = Field(..., description="当前需要生成画面的台词句子")
    index: int = Field(..., description="当前句子序号")
    total_count: int = Field(..., description="总句子数量")


class SingleImageOutput(BaseModel):
    """单张图片生成输出"""
    image_url: str = Field(..., description="生成的图片URL")


# ==================== 节点3：视频合成&字幕 ====================
class VideoComposeInput(BaseModel):
    """视频合成节点输入"""
    image_urls: List[str] = Field(..., description="漫画图片URL列表")
    sentences: List[str] = Field(..., description="对应的台词句子列表")


class VideoComposeOutput(BaseModel):
    """视频合成节点输出"""
    base_video_url: str = Field(..., description="合成后的基础视频URL（无音频）")


# ==================== 节点4：音频嵌入 ====================
class AudioEmbedInput(BaseModel):
    """音频嵌入节点输入"""
    base_video_url: str = Field(..., description="基础视频URL")
    story_text: str = Field(..., description="完整故事文本，用于生成旁白")
    story_type: str = Field(..., description="故事类型，用于匹配BGM")
    enable_narration: bool = Field(default=False, description="是否启用AI旁白朗读")


class AudioEmbedOutput(BaseModel):
    """音频嵌入节点输出"""
    video_with_audio_url: str = Field(..., description="带音频的完整视频URL")


# ==================== 节点5：封面生成&导出 ====================
class CoverExportInput(BaseModel):
    """封面生成导出节点输入"""
    video_with_audio_url: str = Field(..., description="带音频的完整视频URL")
    image_urls: List[str] = Field(..., description="所有漫画图片URL列表")
    story_title: str = Field(..., description="故事标题")


class CoverExportOutput(BaseModel):
    """封面生成导出节点输出"""
    final_video_url: str = Field(..., description="最终导出的MP4视频URL")
    cover_image_url: str = Field(..., description="视频封面图片URL")