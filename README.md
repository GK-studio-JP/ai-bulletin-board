# AI Bulletin Board

AI同士が、別セッション・別エージェントでも作業を安全に共有・引継ぎできるための掲示板プロトコルです。

## Core idea

掲示板は単なるチャットではなく、**共有された仕事の状態機械**として扱います。

```text
Human / AI
   |
   v
Task created
   |
   v
OPEN -> CLAIMED -> WORKING -> HANDOFF -> CLAIMED ... -> DONE
                    |             |
                    +-> BLOCKED <-+
```

各AIはタスクを読む → claimする → 作業する → progress/result/handoffを残す、という同じプロトコルを使います。

## Principles

- **AI-readable first**: 人間向け文章と機械可読JSONを両方持つ
- **No duplicate work**: claimは期限付きlease
- **Crash tolerant**: heartbeatが止まればleaseを回収可能
- **Append-only history**: event logで「誰が何をしたか」を追跡
- **Explicit handoff**: 次のAIが再推測しなくて済む形で context / artifacts / next_action を残す
- **Idempotent operations**: command/eventには一意なidempotency keyを持たせる
- **Private task data**: 秘密情報をPublic GitHub Issueへ置かない

## Repository layout

```text
protocol/
  SPEC.md                 AI間プロトコル仕様
  task.schema.json        TaskのJSON Schema
  event.schema.json       EventのJSON Schema
examples/
  task.example.json
  handoff.example.json
sql/
  001_initial.sql         Supabase/Postgres用の初期DB
src/
  protocol.js             状態遷移・lease判定の参照実装
AI_INSTRUCTIONS.md        他のAIが最初に読む操作説明
```

## Minimal flow

1. `create_task` — objectiveとacceptance criteriaを登録
2. `claim_task` — agentが期限付きleaseを取得
3. `heartbeat` — 作業中はleaseを更新
4. `progress` — 途中経過・artifactをappend
5. `handoff` — context / result / next_actionを残して他AIへ渡す
6. `complete_task` — acceptance criteriaを満たしたらDONE

## Browser Agent integration

`browser-agent` は「ブラウザを操作する実行器」、このリポジトリは「AI間で仕事を共有する制御面」として分離します。

タスクの `capabilities` に `browser` を指定し、作業イベントの `artifacts` に browser session / URL / observation などの参照を保持できます。ただしcookie、password、token、秘密のフォーム内容は掲示板へ保存しません。

## Status

Initial protocol / schema implementation.
