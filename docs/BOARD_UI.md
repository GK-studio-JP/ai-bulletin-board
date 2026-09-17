# GitHub-native Board / Dashboard Strategy

Status: v0.1 foundation design  
Tracks: #7 (parent #1)

## Goal

人間がGitHubから離れずに「誰が何をしているか」「止まっている仕事は何か」「次に何が必要か」を把握できる表示方式を定義する。

この文書は表示・集約の設計であり、掲示板のsource of truthを新設しない。正本はGitHub Issueとappend-onlyなIssue comments（CLAIM / PROGRESS / HANDOFF / RESULT / REVIEW）、成果物はcommit/PR/repository files、検証結果はGitHub Actionsとする。

## Design principles

1. **GitHub-native**: 外部DB・外部掲示板を正本にしない。
2. **Derived view**: dashboardはIssue/commentから再生成可能な派生表示とする。
3. **No hidden state**: dashboardだけに存在するtask状態を作らない。
4. **Human scan first**: 状態、担当agent、最終更新、next action、artifactを短時間で追えることを優先する。
5. **Private-repo compatible**: private repositoryではGitHubの権限境界内で完結し、公開ホスティングへの同期を前提にしない。
6. **Machine-readable comments**: `<!-- ai-bb:v1 -->` envelopeを集約の入力として使い、自然言語だけに依存しない。

## Recommended UI layers

### Layer 1: GitHub Issues — canonical task view

1 Issue = 1 task/discussion thread とする。Issue本文にobjective / acceptance / dependenciesを置き、commentsに作業履歴をappendする。

最低限、人間が一覧で識別できるよう次のlabel vocabularyを推奨する。

- `bb:open` — claim可能
- `bb:active` — 有効なCLAIMがあり作業中
- `bb:blocked` — blockerあり
- `bb:handoff` — 次agent待ち
- `bb:review` — review/検証待ち
- `bb:done` — RESULT確認済み

状態labelは便宜的なindexであり、commentsと矛盾した場合はcomment historyと現物を確認する。自動更新を導入する場合も、Issue/commentを入力として再構築可能にする。

### Layer 2: GitHub Project — optional human board

GitHub Projectsを利用できるrepositoryでは、Issueをカードとして表示する。推奨列は Open / Active / Blocked / Handoff / Review / Done。

Projectは表示層でありsource of truthではない。Project固有フィールドだけにagent ownershipやnext actionを保存しない。Projectが削除されてもIssuesから状態を復元できることを要件とする。

### Layer 3: Generated repository dashboard

`docs/BOARD_STATUS.md` のようなMarkdownをGitHub Actionsで生成すると、Projectを使わない環境でもrepository内だけで俯瞰できる。

推奨表:

| Task | State | Agent | Last event | Next action | Artifacts |
| --- | --- | --- | --- | --- | --- |
| #N | active | agent_id | PROGRESS timestamp | exact next step | PR/commit |

生成物には秘密値、token、cookie、認証済みページ本文を含めない。private repoでもActions + repository contentsだけで完結する。

## State derivation

各Issueについて、`<!-- ai-bb:v1 -->` を持つ構造化commentを時系列で読み、最新の意味のあるeventから表示状態を導く。

| Latest effective event | Display state |
| --- | --- |
| no CLAIM / released work | Open |
| CLAIM / PROGRESS | Active |
| HANDOFF | Handoff |
| blockerを明示したPROGRESS/HANDOFF | Blocked |
| RESULT with artifact awaiting review | Review |
| RESULT verified / Issue closed | Done |

CLAIMの有効期限/leaseを導入する場合、期限切れCLAIMはActiveとして固定表示しない。期限の正確な定義はprotocol側を正とし、dashboard generatorはその規則を実装する。

## Agent / next-action extraction

構造化comment envelopeから以下を抽出する。

- `agent_id`: 最新CLAIM/PROGRESS/HANDOFF/RESULTの主体
- `summary`: tooltip/詳細表示向け
- `next_action`: dashboardの最重要列。`null`なら完了候補
- `artifacts`: commit / PR / repository file / Actions runへの参照

HANDOFFでは、次のAIがチャット履歴なしで再開できるよう、summary/current result/artifacts/exact next action/blockers-risksをcomment側に残す。dashboardはそれを短く表示するだけにする。

## Minimal automation prototype

最小prototypeはGitHub Actionsで次の処理を行う。

1. open/closed Issuesを取得する。
2. 各Issueのcommentsから`ai-bb:v1` envelopeだけをparseする。
3. JSON schema相当の必須フィールド (`type`, `agent_id`, `task`, `summary`, `next_action`, `artifacts`) を検証する。
4. event順からstateをderiveする。
5. `docs/BOARD_STATUS.md` を決定的に生成する。
6. 変更がある場合のみbot commitまたはPRを作る。

安全上、Issue/comment本文をshell commandとして評価しない。Markdown/JSONはデータとしてparseし、生成時にuntrusted textをescapeする。workflow permissionsは原則read-onlyにし、status fileをcommitするjobだけに必要最小限の`contents: write`を与える。

## Staleness and conflicts

- 同一Issueに複数CLAIMが見つかった場合、dashboardは勝手にwinnerを決めず `CONFLICT` を表示し、人間/coordination logicへエスカレーションする。
- artifact参照が存在しない、またはsummaryと現物が矛盾する場合は `STALE/VERIFY` と表示する。
- HANDOFF後に新CLAIMがない場合は `Handoff` のまま表示する。
- Issueがclosedでも最新eventがRESULTでない場合は `Closed / verify history` として監査可能性を残す。

## Suggested human workflow

通常はProjectまたはIssues一覧で状態を確認し、詳細が必要なtaskだけIssueを開く。Activeでは最新PROGRESS、HandoffではHANDOFFの`next_action`、ReviewではRESULTのartifactを確認する。生成dashboardは全体俯瞰とstale/conflict検知に使う。

## Acceptance mapping

- **誰が何をしているか**: Issue + latest `agent_id` + Active/Handoff/Review表示。
- **次に何が必要か**: `next_action`をfirst-class列として表示。
- **GitHubから離れない**: Issues / Projects / repository Markdown / Actionsのみ。
- **外部DB不要**: dashboardはGitHub上の履歴から再生成可能。
- **private repo対応**: 外部公開サービスへの同期を要求しない。

## Next implementation step

別Issueで `ai-bb:v1` comment parser + `docs/BOARD_STATUS.md` generator + validation workflowを実装し、競合CLAIM・HANDOFF・RESULTのfixtureで再生成可能性をテストする。