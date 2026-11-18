# 调查与媒体议题对照

这个 Python 项目整理与“调查与媒体议题对照”有关的来源观察，并生成供研究人员复核的统计摘要。

调查（`SurveyObservation`）与媒体（`Observation`）是两套独立样本：
联合观察（`signal_lab/joint.py`）按月份并列两者，固定调查问题版本、
目标人群与媒体来源范围，分别标注两侧缺失，并把结论限定为并列趋势。
没有有效回答的群体记为缺失而非零关注；媒体报道数量不作为公众意见的
替代值。口径与复现规则见 [docs/analysis-notes.md](docs/analysis-notes.md)。

## 开发

需要 Python 3.11 或更高版本。安装开发依赖：`python -m pip install -e .`。

运行测试：`python -m unittest discover -s tests -v`。
构建发行包：`python -m build`。
