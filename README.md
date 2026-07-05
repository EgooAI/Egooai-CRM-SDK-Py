# EgooAI CRM SDK Py

一个基于 **SQLModel + SQLite** 的轻量 CRM / Session Chat SDK。

## 当前功能

### CRM 基础能力
- `Customer`：客户信息管理
- `Account`：账号信息管理
- `Platform`：平台信息管理
- 支持上述实体的增删改查

### Session / Chat 能力
- `SessionMeta`：会话元数据管理
- 创建 `SessionMeta` 时自动生成唯一 `chatid`
- 创建 `SessionMeta` 时自动创建对应动态聊天表 `sessionchat_<chatid>`
- 删除 `SessionMeta` 时自动删除对应动态聊天表
- `SessionChat`：会话聊天消息管理
- 支持按 `chatid` 操作聊天记录
- 支持按 `sid` 自动路由到对应聊天表

### 数据特性
- 使用 SQLite 持久化数据
- 支持 JSON 字段存储（如 `extra`、`participants`、`content` 等）
- 自动维护 `created_time` / `updated_time`

### 当前测试覆盖
- `CustomerManager`
- `AccountManager`
- `PlatformManager`
- `SessionMetaManager`
- `SessionChatManager`
- 动态聊天表创建、删除与路由逻辑
