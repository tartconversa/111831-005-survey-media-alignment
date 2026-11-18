# 分析口径

## 两类样本，不可互换

项目并行观察两套独立材料，它们不是同一种样本，不能拼成一条"态度变化"序列：

| 集合 | 记录类型 | 数值含义 | 受什么影响 |
| --- | --- | --- | --- |
| 国际民意调查 | `SurveyObservation` | 受访者对某问题的回答（比例/量表值），带有效回答分母 | 受访人群、问法、回答范围、有效回答数 |
| 媒体观察 | `Observation` | 某来源对某主题的**报道数量** | 来源覆盖范围、报道时间、主题归类规则 |

报道数量反映报道覆盖，**不是公众意见，也不能作为公众意见的替代值**。
调查记录与媒体记录在类型上互相隔离：把媒体计数放进调查位、或把调查值
放进媒体位，联合观察构造会直接抛出 `TypeError`。

## 每次联合观察必须固定的选择

`JointObservation`（`signal_lab/joint.py`）在每个月份上并列两侧数据，
并固定记录：

- **调查问题与版本**：`question_id` + `question_version`，连同问法
  （wording）、回答范围（response_scale）保存在 `DefinitionCatalog`；
- **目标人群**：`population_id`，且必须在该问题版本覆盖的人群列表内；
- **媒体来源范围**：`MediaScope`（来源 id 集合、可选地区与语言），
  范围外的报道不计入；
- **有效回答分母**：`survey_valid_responses`，让读者看到比例的样本基础。

## 缺失不等于零

两个集合分别通过 `SeriesGap` 列出缺口，读者可以直接看到各自缺了什么：

- 调查侧 `no_valid_responses`：该群体本周期接受了调查但没有任何有效回答，
  以 `SurveyStatus.NO_VALID_RESPONSES` + `value=None` 记为**缺失**。
  构造器禁止把它写成 0（零关注）；
- 调查侧 `no_record`：该周期根本没有这个人群的调查记录，同样不能推断为零；
- 媒体侧 `no_observation` / `no_coverage`：范围内没有观察记录，或有观察
  但未覆盖该主题——报道计数为零与数据缺失无法区分，统一按缺失呈现。

## 结论只能是并列趋势

联合观察的 `interpretation` 只有 `PARALLEL_TREND` 一种取值，
`supports_association()` 恒为 `False`。每条观察固定附带提示：

- 两侧仅为时间上并列的趋势，样本相互独立，不支持关联或因果结论；
- 媒体值是报道数量，不是公众意见或其替代值。

时间相近不能被表述成同一群体的态度变化。

## 版本更新与旧报告复现

问卷问题（`SurveyQuestion`）与主题定义（`TopicDefinition`）在
`DefinitionCatalog` 中**只增不改**：口径更新登记为新版本并标注生效日期。

- 新分析按周期当天生效的版本取口径（`question_version_on` /
  `topic_version_on`），问卷改版后的月份自动采用新版本；
- `JointAnalysisReport` 固定每条观察使用的问题版本与主题版本，并保存
  规范化输入摘要 `input_digest`；
- `reproduce_joint_report()` 按报告固定的版本从目录取回同一定义，
  用当时的输入与来源选择重新构造并比对摘要。即使目录后来加入了新版本，
  旧报告仍可按当时输入和选择复现；输入或选择一旦变化，复现结果会列出
  不一致的观察 id。
