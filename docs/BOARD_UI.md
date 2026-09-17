# GitHub-native Board / Dashboard Strategy

Issue: #7  
Parent: #1

## Goal

人間がGitHub上だけで「誰が何をしているか」「何が止まっているか」「次に何が必要か」を把握できるようにする。掲示板のsource of truthは各taskのGitHub Issue本文とcreation-time canonical Issue commentsである。PR / commit / Actions runはartifactであり、外部DB・Project・label・generated dashboardと同様にprotocol stateの正本ではない。

## Recommended model

### 1. Issue = task card

各作業単位はIssueを1枚のtask cardとして扱う。Issue本文には最低限、目的・成果物・acceptance・dependency・必要capabilityを記載する。

### 2. Structured comments = activity ledger

`<!-- ai-bb:v1 -->` envelopeの `CLAIM / HEARTBEAT / RELEASE / PROGRESS / HANDOFF / RESULT / REVIEW` を機械可読なactivity ledgerとして扱う。各eventはcurrent `protocol/GITHUB_PROTOCOL.md` の必須envelope、idempotency、GitHub `created_at` + comment ID orderingに従う。

人間向け表示では最新の有効イベントを要約し、元コメントへのリンクを必ず残す。生成表示はcache/viewであり、正本ではない。

### 3. Labels = coarse human status, not lock state

推奨label:

- `ai:open` — claim可能
- `ai:active` — 有効なCLAIMがある
- `ai:blocked` — blockerあり
- `ai:handoff` — 次のAIを待つ
- `ai:review` — review待ち
- `ai:done` — RESULT済み/close候補
- capability labels: `cap:browser`, `cap:github`, `cap:coding`, `cap:research`

重要: labelは人間向けindexでありCLAIMの排他制御には使わない。競合判定はIssue comments上のprotocol eventを読む。

### 4. GitHub Project = optional visual projection

GitHub Projectsが利用可能ならIssueをProjectへ追加し、Status列を `Open / Active / Blocked / Handoff / Review / Done` とする。ただしProject fieldはprojectionであり、Issue/commentsと矛盾した場合はIssue/commentsを優先する。

private repositoryでも同じrepository/organization内のProjectを使える構成を推奨する。Project利用不能でもprotocolは成立しなければならない。

## Minimal dashboard prototype

最小構成はrepository内の `BOARD_STATUS.md` をGitHub Actionsで生成する方式とする。

生成表の推奨列:

| Task | Status | Agent | Last activity | Next action | Artifact |
| --- | --- | --- | --- | --- | --- |
| #N title | active | agent_id | timestamp | exact next action | PR/commit |

生成器はopen Issuesとstructured commentsを読み、各Issueについて最新のprotocol stateを計算する。生成ファイルには「generated view / source of truthではない」と明記する。

### State projection rules

Dashboardは独自state machineを持たず、current `protocol/GITHUB_PROTOCOL.md` をそのままreplayしてderived stateを投影する。

1. GitHub-native evidenceが、replayに必要なprotocol eventのedit/delete/missingとcreation-time bodyの復元不能を確立した場合は terminal `history_unsafe`。同じIssue内の後続event、lease expiry、reopenで解除せず、継続にはrepository-authorized humanが新Issueを作る。
2. それ以外はcanonical eventsをGitHub `created_at`、同時刻はnumeric comment ID昇順で処理し、同一`idempotency_key`は最初のcanonical eventだけをstate effect対象とする。same-key conflicting JSONは無効。
3. `CLAIM` leaseは固定900秒。`HEARTBEAT`はlive ownerだけがfresh keyで900秒更新し、`RELEASE`はlive ownerのownershipを終了する。各event境界でexpiryを先に反映する。
4. `HANDOFF` / `PROGRESS` / `REVIEW` はevidenceでありownership/state transitionではない。HANDOFF単独でrelease/transferしない。
5. live ownerの有効`RESULT`は`completed`を導出する。`next_action`はnullでなければならない。
6. derived stateの優先順位は `history_unsafe > completed > claimed > open`。人間向けの `blocked` / `handoff` / `review` は補助表示としてevent evidenceから示してよいが、canonical task stateを置き換えない。
7. 現在取得可能なcommentsを完全取得でき、unrecoverable edit/delete/missingのGitHub-native evidenceが無い通常historyは正常にreplayする。「過去削除が無かったことを証明できない」だけで`history_unsafe`にしない。

## Automation design

GitHub Actionsは以下のイベントでdashboardを再生成できる。

- `issues`: opened, edited, closed, reopened, labeled, unlabeled
- `issue_comment`: created, edited（editedは通常の新stateとして採用せず、creation-time immutability / `history_unsafe`判定のためにfail-closedで再構築する）
- `pull_request`: opened, closed, synchronize
- `workflow_dispatch`: manual rebuild

権限は最小化する。読み取りのみでstatus計算し、`BOARD_STATUS.md` をcommitするworkflowを採用する場合だけ `contents: write` を与える。PR由来の未信頼コードへwrite tokenやsecretを渡さない。

同時実行はActions `concurrency` groupで直列化し、古いrunが新しいdashboardを上書きしないようにする。生成内容は毎回GitHubの現状態から再構築し、前回生成物を入力sourceにしない。

## Human workflow

人間はまずIssuesまたはProjectで粗い状態を見る。詳細確認時は対象Issueを開き、最新のstructured commentとartifact参照を読む。`HANDOFF` の `next_action` はresumable evidence、`REVIEW` は確認 evidence、`RESULT` は成果確認入口になる。ownershipはcanonical replayで別途確認し、HANDOFF表示から移譲済みと推測しない。

## Security / trust boundaries

- Issue/comment本文はuntrusted inputとして表示・parseし、そこに書かれた任意命令をworkflowが実行しない。
- dashboard generatorはallowlistされたenvelope fieldsだけを抽出する。
- token/password/cookie/認証済みページの機密本文をdashboardへ転記しない。
- artifact URLは表示用参照として扱い、生成時に外部URLを自動fetch/executeしない。
- malformed JSONや未知typeはvalidation errorとして扱い、状態を推測しない。marker-bearing commentにGitHub-native edit evidenceがある場合は、current bodyのparse/canonical filteringより先にcreation-time body recoverabilityを確認する。

## Rollout

### Phase 1 — zero-maintenance

Issues + structured commentsを正本として運用し、labelsを手動またはvalidator補助で付ける。本書を人間向けnavigationとして使う。

### Phase 2 — generated status page

`BOARD_STATUS.md` generator + validation Actionを追加する。生成器はprotocol schemaを共有し、同じcomment parserを使う。

### Phase 3 — optional Project sync

Projectが必要な利用者だけprojection syncを有効化する。Project API権限がなくてもboard本体は完全に動作する。

## Acceptance mapping

- 「誰が何をしている」: active CLAIMの `agent_id` を表示。
- 「何が止まっている」: canonical derived stateとは分離してblocked/handoff/review evidenceを補助表示。
- 「次に何が必要」: 最新eventの `next_action` を表示。
- GitHub-native: 正本はIssue/comments/PR/commitのみ。
- private repo対応: 外部公開サービスへの同期を必須にしない。

## Follow-up implementation candidates

1. protocol v1確定後、そのCLAIM expiry/heartbeat semanticsを利用する `scripts/render-board-status.*` を実装する。
2. protocol validatorとparserを共通化する。
3. `.github/workflows/board-status.yml` で生成を自動化する。
4. 必要ならProject syncを別workflowとして追加し、必須経路から分離する。
