## 项目概述
- **名称**: 火柴人剧情漫画故事视频生成工作流
- **功能**: 输入完整故事文本，自动生成黑白火柴人漫画分镜视频（含字幕+BGM），适配抖音短视频

### 节点清单
| 节点名 | 文件位置 | 类型 | 功能描述 | 分支逻辑 | 配置文件 |
|-------|---------|------|---------|---------|---------|
| split_story | `nodes/split_story_node.py` | agent | 智能语义分句，拆分台词识别故事类型 | - | `config/split_story_llm_cfg.json` |
| generate_images | `nodes/generate_images_node.py` | task | 并行生成火柴人漫画分镜图片 | - | - |
| video_compose | `nodes/video_compose_node.py` | task | 本地ffmpeg合成：视频+字幕+BGM | - | - |
| cover_export | `nodes/cover_export_node.py` | task | 生成封面，导出最终视频 | - | - |
| single_image_gen | `nodes/single_image_gen_node.py` | task | 单张漫画图片生成（子图节点） | - | - |

**类型说明**: task(任务节点) / agent(大模型节点) / condition(条件分支) / looparray(列表循环) / loopcond(条件循环)

## 子图清单
| 子图名 | 文件位置 | 功能描述 | 被调用节点 |
|-------|---------|------|---------|-----------|
| image_gen_subgraph | `graphs/loop_graph.py` | 循环生成单张漫画图片 | generate_images |

## 技能使用
- `split_story_node`: 使用大语言模型技能（LLMClient）进行智能分句
- `generate_images_node`: 使用图片生成技能（ImageGenerationClient）生成漫画分镜
- `video_compose_node`: 使用ffmpeg本地合成视频，ASS字幕格式，和弦BGM
- `cover_export_node`: 使用图片生成技能生成封面 + 对象存储上传

## 工作流流程
```
[用户输入故事文本]
    ↓
[智能语义分句] → 拆分台词 + 识别类型 + 提取标题
    ↓
[并行图片生成] → 每句台词生成一张火柴人漫画
    ↓
[本地视频合成] → ffmpeg生成视频 + ASS字幕 + BGM音频（一次性完成）
    ↓
[封面生成&导出] → 高潮画面封面 + 最终MP4输出
```

## 视频规格
- **分辨率**: 1080x1920 (9:16竖屏)
- **帧率**: 30fps
- **单图时长**: 3秒
- **字幕样式**: ASS格式，白色字体+半透明黑色底色(40%不透明度)+圆角矩形背景
- **BGM**: 和弦风格正弦波（频率根据故事类型调整：励志440Hz/亲情392Hz/感悟330Hz/治愈262Hz）

## 字幕配置（ASS格式）
```
Style: Default,WenQuanYi Zen Hei,42,&H00FFFFFF,&H000000FF,&H00000000,&HA0000000,1,0,0,0,100,100,0,0,1,3,0,2,50,50,100,1
```
- FontName: WenQuanYi Zen Hei（粗黑体）
- FontSize: 42
- PrimaryColour: 白色
- BackColour: 半透明黑色（&HA0000000 = 40%不透明度）
- Outline: 3（描边）
- Alignment: 2（底部居中）
- MarginL/R: 50（左右留白）

## 画风规范
- **正向提示词**: 黑白线条火柴人漫画，完整场景与环境道具，人物互动自然，极简手绘风格
- **负面提示词**: 极简单线无场景，空白背景，彩色画面，人物五官，卡通/3D画风，水印文字