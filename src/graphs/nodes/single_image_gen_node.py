# 单张图片生成节点（子图使用）
# 为单个句子生成对应的彩色漫画分镜图

import os
import logging
from typing import List
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from coze_coding_dev_sdk import ImageGenerationClient

from graphs.state import SingleImageInput, SingleImageOutput

logger = logging.getLogger(__name__)


# 固定正向绘图提示词（全局通用）- 彩色漫画风格，专业插画质感
POSITIVE_PROMPT_TEMPLATE = """9:16竖屏抖音短视频分镜，彩色漫画风格，专业插画师级手绘艺术，电影级分镜构图，高质量叙事漫画，鲜艳色彩，丰富层次。

【核心画面构成】
- 主角人物：清晰的人物轮廓，精致的面部表情，动态姿态有张力，服饰细节丰富，位置突出在画面焦点
- 配角人物：如有互动场景，配角形象与主角呼应，姿态协调，形成人物关系张力
- 完整场景构建：绝不是空白背景，必须有具体场景空间，场景元素丰富

【人物设计】
- 简约漫画人物：不是写实真人，保持漫画风格
- 面部表情：眼睛嘴巴鼻子简约但有表达力，能传递情绪
- 服饰设计：衣服褶皱、颜色搭配、款式细节
- 手脚细节：手指动作、鞋子款式、肢体比例协调
- 头发设计：发型轮廓、发丝走向、颜色深浅

【场景细节要求】（根据剧情自动匹配）
室内场景深度细节：
- 建筑结构：墙壁纹理、砖缝线条、门窗框架、楼梯台阶、天花板横梁
- 家具陈设：桌椅沙发床柜、书架排列、茶具餐具、台灯吊灯、地毯纹样
- 生活道具：书籍堆叠、杯瓶摆放、衣物悬挂、照片海报、钟表电器
- 光影氛围：窗户投射的光线、灯具散发的光晕、墙面的明暗过渡

室外场景深度细节：
- 城市街道：建筑立面颜色多样、招牌霓虹彩色、门窗橱窗、路灯柱子、车辆行人
- 自然风景：树木绿叶、草地花朵彩色、远山轮廓、河流水面、天空云朵
- 天气氛围：阳光穿透金黄色、雨滴落下、风吹草动、暮色晨光橙红色、月夜星光
- 空间透视：道路延伸、建筑远近、人物大小比例、透视线条正确

【色彩系统】
- 主色调：根据剧情情绪选择（温暖橙色系/冷静蓝色系/治愈绿色系/励志红色系）
- 人物颜色：服饰有颜色区分，肤色自然柔和，头发颜色多样
- 场景颜色：背景有层次色彩，道具颜色丰富但不杂乱
- 光影颜色：光源颜色（暖光/冷光），阴影颜色深浅变化
- 色彩和谐：整体色调统一，不出现突兀的颜色冲突

【构图技法】
- 三层深度：前景人物动态清晰、中景互动道具丰富、远景背景氛围烘托
- 视角选择：平视、俯视、仰视根据剧情情绪调整，增强视觉冲击
- 留白设计：画面边缘适度留白，主体区域饱满，构图平衡不拥挤
- 起承转合：画面有故事开端发展高潮结尾的叙事节奏感

【线条技法】
- 轮廓主线条：清晰线条勾勒人物和主要物体，边缘干净
- 细节次线条：细腻线条描绘纹理装饰，精致入微
- 阴影渲染：柔和渐变表现明暗，营造体积感和氛围
- 动态表现：人物动作用流畅线条，静止物体用稳定线条

【氛围营造】
- 光影渲染：光源方向明确，阴影形状正确，明暗过渡柔和
- 情绪表达：画面氛围与剧情情感一致（温馨暖色调/励志明亮色调/治愈柔和色调/哲理深沉色调）
- 时间感：昼夜晨暮、春夏秋冬、通过光线色调表达
- 故事感：画面本身就是一个小故事，观者一眼就能理解剧情

【质量标准】
- 高清画质：线条清晰色彩饱满，无模糊噪点，印刷级画质
- 专业构图：符合漫画分镜规范，可直接用于商业出版
- 细节丰富：画面元素不少于20个，色彩层次分明
- 故事完整：单张画面就能传达完整剧情片段
- 画风统一：彩色漫画风格，全程保持一致

禁止：空白背景、火柴人极简风格、黑白单色、无场景道具、真人照片、文字水印、过度卡通萌化、3D渲染、过度黑暗、杂乱无章。

风格：彩色叙事漫画，手绘治愈风格，电影分镜质感，专业插画师水准。
内容：根据以下剧情创作完整彩色分镜画面 - {sentence}"""

# 固定负面提示词（强制避雷）
NEGATIVE_PROMPT = """火柴人极简风格，空白白色背景，单一场景无细节，黑白单色画面，真人照片写实，过度卡通萌系，3D渲染，照片写实，水印，画面自带文字标题，杂乱无章，夸张特效滤镜，低清模糊噪点，写实人物照片，动漫美型过度，过度阴影黑暗，线条过于简单，人物无五官表情"""


def single_image_gen_node(
    state: SingleImageInput,
    config: RunnableConfig,
    runtime: Runtime[Context]
) -> SingleImageOutput:
    """
    title: 单张彩色漫画分镜生成
    desc: 根据单句台词内容生成对应的彩色漫画分镜图，9:16竖屏，丰富色彩和细节
    integrations: 图片生成
    """
    ctx = runtime.context
    
    # 获取输入参数
    sentence: str = state.sentence
    sentence_index: int = state.index
    total_sentences: int = state.total_count
    
    # 构建提示词
    positive_prompt = POSITIVE_PROMPT_TEMPLATE.replace("{sentence}", sentence)
    
    logger.info(f"[Image Gen] Generating image for sentence {sentence_index + 1}/{total_sentences}")
    logger.info(f"[Image Gen] Sentence: {sentence[:50]}...")
    
    # 初始化图片生成客户端
    image_client = ImageGenerationClient(ctx=ctx)
    
    try:
        # 调用图片生成API
        # 使用通用模型生成彩色漫画
        result = image_client.generate(
            prompt=positive_prompt,
            negative_prompt=NEGATIVE_PROMPT,
            width=1080,
            height=1920,  # 9:16竖屏
            model="doubao-seedream-3-0-t2i-250415"  # 使用高质量图片生成模型
        )
        
        # 获取生成的图片URL
        if result and len(result) > 0:
            image_url = result[0].url if hasattr(result[0], 'url') else result[0]
            logger.info(f"[Image Gen] Image generated successfully: {image_url}")
        else:
            raise Exception("图片生成返回空结果")
            
    except Exception as e:
        logger.error(f"[Image Gen] Image generation failed: {e}")
        raise Exception(f"图片生成失败: {e}")
    
    return SingleImageOutput(
        image_url=image_url,
        sentence_index=sentence_index
    )