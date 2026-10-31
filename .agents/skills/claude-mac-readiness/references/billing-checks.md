# 已付款与账号计划不一致时的检查

仅用于用户报告已付款仍显示 Free、网页与 Code 额度不同，或需要解释自己提供的账单。帮助定位状态，不代办订阅、开户、转账、KYC 或退款。

首次订阅或比较渠道先读 [账号与订阅准备](account-preparation.md)；涉及错误、身份核验或凭据问题时读 [事故分流](incident-and-cleanup.md)。已有正常账号和付款记录按实际事实复用。

## 先确定产品与扣款渠道

| 所用产品/入口 | 核对位置与边界 |
| --- | --- |
| Claude 网页 Pro/Max | 用户本人查看对应账号的 Settings → Billing、当期计划和最近付款状态 |
| Claude iOS/Android 内购 | Apple App Store/Google Play 管理付款方式、收据与订阅；先确认实际购买渠道，不在网页重复购买 |
| Console/API、OpenRouter 或云提供方 | 独立核对该服务的余额/计费与 CLI 实际认证来源；不能把聊天订阅当 API 余额 |

网页与移动端的账单归属按 [Claude 官方账单说明](https://support.claude.com/en/articles/8325618-paid-plan-billing-faqs)核对，订阅与 API 按 [独立计费说明](https://support.claude.com/en/articles/9876003-i-have-a-paid-claude-subscription-pro-max-team-or-enterprise-plans-why-do-i-have-to-pay-separately-to-use-the-claude-api-and-console)区分。

## 用最少信息定位

1. 确认客户端使用的是购买时的同一账号；仅要求用户核对，不收集完整邮箱、银行卡、地址、身份资料或订单访问链接。
2. 区分付款成功、订阅当前生效、CLI 采用该订阅三件事。Receipt 中的已付记录只支持特定历史交易；Invoice 需看应付/已付/余额与状态，文件名不能证明付款。PDF 不构成真实性或当期账号状态的独立验证。
3. 用户在官方界面核对最近付款失败、取消/到期、计划生效和实际错误，再结合 CLI 认证覆盖排查。记录必要结果；不要为了测试重新购买、清登录状态或换新号。
4. Apple／Google Play 已扣未开通时，分别核对商店账号下的实际订阅与当前 Claude 应用账号；按当期官方 App 的恢复购买或原渠道支持流程处理，不预设订阅可迁移，也不去另一渠道再买。
5. 涉及身份验证时查 [当前官方说明](https://support.claude.com/en/articles/14328960-identity-verification-on-claude)，由用户本人处理；不预设必须美国 SSN、不推测必封，也不指导选择虚假地区或地址。

## 外部支付教程的用途

第三方卡平台、内购或礼品卡清单只可提供核验线索。准入、实际居住地、商店地区、支付资料、商户支持和活动各有条件，支付成功也不改变服务地区要求。没有样本量、失败分母与观察期限的“99%/100%”不作为成功率或采购排名。

官方允许的支付方式以当期渠道为准。教程若要求荐码、私聊短链或不透明代充，先识别其主体与条件，不替用户打开或填写敏感资料。普通环境排障无需加载银行开户和数字资产转账流程。
