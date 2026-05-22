CREATE DATABASE IF NOT EXISTS changelog_db;

CREATE TABLE IF NOT EXISTS changelog_db.snapshots
(
    project_name      String,
    snapshot_version  UInt16,
    status_date       Date,
    parsed_at         DateTime DEFAULT now(),
    updated_at        DateTime DEFAULT now(),
    uid               UInt32,
    id                UInt32 DEFAULT 0,
    wbs               String DEFAULT '',
    name              String,
    level             UInt8 DEFAULT 0,
    outline           String DEFAULT '',
    parent_uid        UInt32 DEFAULT 0,
    summary           String DEFAULT 'N',
    milestone         String DEFAULT 'N',
    start             Nullable(Date),
    finish            Nullable(Date),
    baseline_start    Nullable(Date),
    baseline_finish   Nullable(Date),
    duration          String DEFAULT '',
    pct_complete      UInt8 DEFAULT 0,
    actual_start      Nullable(Date),
    actual_finish     Nullable(Date),
    cost              Float64 DEFAULT 0,
    baseline_cost     Float64 DEFAULT 0,
    work              Float64 DEFAULT 0,
    baseline_work     Float64 DEFAULT 0,
    predecessors      String DEFAULT '',
    resources         String DEFAULT '',
    notes             String DEFAULT ''
)
ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY project_name
ORDER BY (project_name, snapshot_version, uid)
SETTINGS index_granularity = 256;

CREATE TABLE IF NOT EXISTS changelog_db.strategic_control
(
    project_name          String,
    uid                   UInt32,
    wbs                   String DEFAULT '',
    name                  String,
    summary               String DEFAULT 'N',
    baseline_finish       Nullable(Date),
    current_finish        Nullable(Date),
    delta_baseline_days   Int32 DEFAULT 0,
    escalation            UInt8 DEFAULT 0,
    ai_strategic_analysis String DEFAULT '',
    snapshot_version      UInt16,
    updated_at            DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY project_name
ORDER BY (project_name, uid)
SETTINGS index_granularity = 256;

CREATE TABLE IF NOT EXISTS changelog_db.change_log
(
    project_name        String,
    log_id              String,
    snapshot_from       UInt16,
    snapshot_to         UInt16,
    date                Date,
    uid                 UInt32,
    wbs                 String DEFAULT '',
    name                String DEFAULT '',
    level               UInt8 DEFAULT 0,
    change_type         String,
    delta_start_days    Int32 DEFAULT 0,
    delta_finish_days   Int32 DEFAULT 0,
    delta_baseline_days Int32 DEFAULT 0,
    category_code       String DEFAULT 'UNKNOWN',
    technical_summary   String DEFAULT '',
    impact_type         String DEFAULT '',
    confidence          Float32 DEFAULT 0.0,
    warnings            String DEFAULT '',
    escalation_required UInt8 DEFAULT 0,
    expert_comment      String DEFAULT '',
    status              String DEFAULT 'Pending',
    updated_at          DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY project_name
ORDER BY (project_name, log_id)
SETTINGS index_granularity = 256;

CREATE TABLE IF NOT EXISTS changelog_db.classifier
(
    code        String,
    category    String,
    group_name  String,
    description String,
    impact      String
)
ENGINE = MergeTree()
ORDER BY code;

INSERT INTO changelog_db.classifier VALUES
  ('OPT-TECH',  'Технол. оптимизация',  'Технологическая',  'Изменение режима, объединение пробоотборов',  'Ускорение'),
  ('OPT-RES',   'Оптимизация ресурсов', 'Технологическая',  'Добавление персонала, перераспределение',      'Ускорение'),
  ('OPT-SCOPE', 'Оптимизация объёма',   'Технологическая',  'Сокращение экспериментов по решению команды',  'Ускорение'),
  ('DELAY-EXT', 'Внешняя задержка',     'Ресурсная',        'Поставка реагентов, срыв подрядчиком',         'Задержка'),
  ('DELAY-INT', 'Внутренняя задержка',  'Ресурсная',        'Ошибка методики, задержка согласования',       'Задержка'),
  ('DELAY-TECH','Технол. препятствие',  'Ресурсная',        'Повторный прогон, отказ оборудования',         'Задержка'),
  ('SCOPE-ADD', 'Расширение объёма',    'Организационная',  'Новые эксперименты, дополнительный раздел ОТР','Перепланирование'),
  ('REPLAN',    'Ошибка планирования',  'Организационная',  'Неверная оценка трудоёмкости',                 'Перепланирование'),
  ('UNKNOWN',   'Нет данных',           '—',                'Текст пустой или бессмысленный',               '—');

CREATE TABLE IF NOT EXISTS changelog_db.project_meta
(
    project_name      String,
    ms_project_name   String DEFAULT '',
    status_date       Date,
    project_start     Nullable(Date),
    project_finish    Nullable(Date),
    last_parsed_at    DateTime DEFAULT now(),
    last_version      UInt16 DEFAULT 1,
    total_tasks       UInt32 DEFAULT 0,
    summary_tasks     UInt32 DEFAULT 0,
    milestones        UInt32 DEFAULT 0,
    leaf_tasks        UInt32 DEFAULT 0,
    with_baseline     UInt32 DEFAULT 0,
    total_resources   UInt32 DEFAULT 0,
    updated_at        DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY project_name;
