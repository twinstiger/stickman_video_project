# 单张图片生成节点（子图使用）
# 为单个句子生成对应的火柴人漫画分镜图

import os
from typing import List
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from coze_coding_dev_sdk import ImageGenerationClient

from graphs.state import SingleImageInput, SingleImageOutput


# 固定正向绘图提示词（全局通用）- 极丰富画面细节，专业漫画分镜质感
POSITIVE_PROMPT_TEMPLATE = """9:16竖屏抖音短视频分镜，黑白线条火柴人漫画风格，专业插画师级手绘艺术，电影级分镜构图，高质量叙事漫画。

【核心画面构成】
- 主角火柴人：清晰的人物轮廓线条，动态姿态有张力，肢体动作表达情感，位置突出在画面焦点
- 配角火柴人：如有互动场景，配角形象与主角呼应，姿态协调，形成人物关系张力
- 完整场景构建：绝不是空白背景，必须有具体场景空间

【场景细节要求】（根据剧情自动匹配）
室内场景深度细节：
- 建筑结构：墙壁纹理、砖缝线条、门窗框架、楼梯台阶、天花板横梁
- 家具陈设：桌椅沙发床柜、书架排列、茶具餐具、台灯吊灯、地毯纹样
- 生活道具：书籍堆叠、杯瓶摆放、衣物悬挂、照片海报、钟表电器
- 光影氛围：窗户投射的光线、灯具散发的光晕、墙面的明暗过渡、角落的阴影层次

室外场景深度细节：
- 城市街道：建筑立面、招牌霓虹、门窗橱窗、路灯柱子、车辆行人
- 自然风景：树木枝叶、草地花朵、远山轮廓、河流水面、天空云朵
- 天气氛围：阳光穿透、雨滴落下、风吹草动、暮色晨光、月夜星光
- 空间透视：道路延伸、建筑远近、人物大小比例、透视线条正确

【构图技法】
- 三层深度：前景人物动态清晰、中景互动道具丰富、远景背景氛围烘托
- 视角选择：平视、俯视、仰视根据剧情情绪调整，增强视觉冲击
- 留白设计：画面边缘适度留白，主体区域饱满，构图平衡不拥挤
- 起承转合：画面有故事开端发展高潮结尾的叙事节奏感

【线条技法】
- 轮廓主线条：粗实线条勾勒人物和主要物体，清晰醒目
- 细节次线条：细柔线条描绘纹理装饰，精致入微
- 阴影排线：疏密线条表现明暗，营造体积感和氛围
- 动态线条：人物动作用流畅线条，静止物体用稳定线条
- 边缘处理：线条断续有节奏，不全是闭合僵硬轮廓

【氛围营造】
- 光影渲染：光源方向明确，阴影形状正确，明暗过渡柔和
- 情绪表达：画面氛围与剧情情感一致（温馨/励志/治愈/哲理）
- 时间感：昼夜晨暮、春夏秋冬、通过光线色调线条表达
- 故事感：画面本身就是一个小故事，观者一眼就能理解剧情

【质量标准】
- 高清线条：线条清晰流畅，无模糊断线，印刷级画质
- 专业构图：符合漫画分镜规范，可直接用于商业出版
- 细节丰富：画面元素不少于15-20个，层次分明
- 故事完整：单张画面就能传达完整剧情片段
- 画风统一：黑白极简手绘风格，全程保持一致

禁止：空白背景、单一火柴人、无场景道具、彩色元素、真人五官、文字水印、卡通萌化、3D渲染、过度黑暗、杂乱无章。

风格：黑白叙事漫画，手绘治愈风格，电影分镜质感，专业插画师水准。
内容：根据以下剧情创作完整分镜画面 - {sentence}"""

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