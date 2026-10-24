BEGIN;

-- 1. Create a system administrator / reviewer account for seeding
INSERT INTO users (user_id, email, password_hash, role)
VALUES ('00000000-0000-0000-0000-000000000001', 'admin@careeradapt.local', 'DISABLED-NO-LOGIN', 'admin')
ON CONFLICT (user_id) DO NOTHING;

-- 2. Career Version: Data Analyst v3.0
INSERT INTO career_versions (career_version_id, career_code, version_tag, status, source_references, published_at)
VALUES (
    '10000000-0000-0000-0000-000000000001',
    'DATA_ANALYST',
    'v3.0',
    'draft',
    '[
        {"source": "O*NET", "code": "15-2051.01", "name": "Business Intelligence Analysts"},
        {"source": "ESCO", "code": "2511", "name": "Data Analyst"}
    ]'::jsonb,
    now()
) ON CONFLICT (career_code, version_tag) DO NOTHING;

-- 3. Skill Requirements (Total weight = 1.000, Target Level 1-2)
INSERT INTO skill_requirements (career_version_id, skill_code, target_level, weight, is_core, rubric_definition)
VALUES 
(
    '10000000-0000-0000-0000-000000000001',
    'SQL',
    2,
    0.300,
    TRUE,
    '{"0": "Khong truy van duoc du lieu hoac sai logic cot loi", "1": "Loc va tong hop co ban nhung con sai sot", "2": "Tong hop dung theo thang/vung, xu ly dung cac quy tac", "3": "Xu ly them truong hop bien va kiem tra cheo tong"}'::jsonb
),
(
    '10000000-0000-0000-0000-000000000001',
    'PYTHON',
    1,
    0.150,
    FALSE,
    '{"0": "Khong chay duoc code hoac sai thu vien", "1": "Phan tich co ban voi Pandas, doc va lam sach nhe", "2": "Xu ly du lieu doc lap, tinh toan dung", "3": "Toi uu hoa code va xu ly ngoai le phuc tap"}'::jsonb
),
(
    '10000000-0000-0000-0000-000000000001',
    'DATA_QUALITY',
    2,
    0.200,
    TRUE,
    '{"0": "Khong nhan dien duoc loi du lieu", "1": "Nhan dien va xu ly dung mot phan loi du lieu", "2": "Xu ly du va giai thich duoc viec lam sach", "3": "Co nhat ky audit va phan tich rui ro chat luong"}'::jsonb
),
(
    '10000000-0000-0000-0000-000000000001',
    'DATA_VIZ',
    2,
    0.200,
    FALSE,
    '{"0": "Chon sai hoan toan bieu do hoac gay hieu nham", "1": "Chon duoc bieu do phu hop nhung thieu nhan/chu thich", "2": "Bieu do ro rang, day du nhan, don vi va tieu de", "3": "Ket noi visual voi insight kinh doanh va de xuat"}'::jsonb
),
(
    '10000000-0000-0000-0000-000000000001',
    'WRITTEN_EXPLANATION',
    2,
    0.150,
    FALSE,
    '{"0": "Khong giai thich duoc hoac dua so lieu sai", "1": "Giai thich roi rac, chua gan voi so lieu thuc te", "2": "Ket luan ro rang dua tren so lieu va neu duoc gioi han", "3": "Giao tiep suc tich, de hieu cho nguoi khong chuyen"}'::jsonb
)
ON CONFLICT (career_version_id, skill_code) DO NOTHING;

-- Publish Career Version now that weights sum to exactly 1.000
UPDATE career_versions 
SET status = 'published' 
WHERE career_version_id = '10000000-0000-0000-0000-000000000001';

-- 4. Tin tuyển dụng: KHÔNG seed ở đây.
-- Chỉ nạp tin thật do nhóm tự thu thập (có link và ngày lấy tin thật), bằng bước nạp riêng sau.

-- 5. Tasks DA01, DA02, DA03
INSERT INTO task_versions (
    task_version_id, career_version_id, task_code, variant_code, version_tag, title,
    duration_minutes, skill_codes, input_dataset_ref, reference_output_ref,
    deterministic_rules, rubric, status, is_active, published_at
)
VALUES
(
    '20000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    'DA01',
    'A',
    'v1.0',
    'Lam sach va tong hop du lieu ban hang (DA01A)',
    35,
    ARRAY['SQL', 'DATA_QUALITY'],
    'datasets/da01a_input.csv',
    'datasets/da01a_ref.csv',
    '{"row_check": "10 -> 9 -> 8", "valid_completed_rows": 7, "total_revenue": 1170000, "region_revenue": {"Nam": 700000, "Bac": 370000, "Unknown": 100000}, "mom_pct": -14.29}'::jsonb,
    '{"criteria": [{"id": "DA01_SQL", "weight": 0.5}, {"id": "DA01_QUALITY", "weight": 0.5}]}'::jsonb,
    'published',
    TRUE,
    now()
),
(
    '20000000-0000-0000-0000-000000000002',
    '10000000-0000-0000-0000-000000000001',
    'DA02',
    'A',
    'v1.0',
    'Phan tich du lieu Python va ve bieu do (DA02A)',
    40,
    ARRAY['PYTHON', 'DATA_VIZ'],
    'datasets/da02a_input.csv',
    'datasets/da02a_ref.csv',
    '{"python_check": "clean_dataframe", "viz_check": "chart_has_labels"}'::jsonb,
    '{"criteria": [{"id": "DA02_PY", "weight": 0.5}, {"id": "DA02_VIZ", "weight": 0.5}]}'::jsonb,
    'published',
    TRUE,
    now()
),
(
    '20000000-0000-0000-0000-000000000003',
    '10000000-0000-0000-0000-000000000001',
    'DA03',
    'A',
    'v1.0',
    'Viet bao cao va nhan xet tu so lieu (DA03A)',
    25,
    ARRAY['WRITTEN_EXPLANATION'],
    'datasets/da03a_input.csv',
    'datasets/da03a_ref.txt',
    '{"max_words": 120, "has_metric_citation": true}'::jsonb,
    '{"criteria": [{"id": "DA03_COMM", "weight": 1.0}]}'::jsonb,
    'published',
    TRUE,
    now()
)
ON CONFLICT (task_code, variant_code, version_tag) DO NOTHING;

-- 6. Learning Activity Catalog (Insert as 'draft' first to allow prerequisites setup)
INSERT INTO activity_catalog (activity_id, career_version_id, activity_code, title, skill_code, estimated_hours, required_output, status)
VALUES
(
    '30000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    'ACT_SQL_01',
    'Truy van SQL co ban & Tong hop du lieu',
    'SQL',
    4.0,
    'Tap tin truy van SQL giai bai toan groupby va filter',
    'draft'
),
(
    '30000000-0000-0000-0000-000000000002',
    '10000000-0000-0000-0000-000000000001',
    'ACT_SQL_02',
    'Kiem tra va lam sach du lieu voi SQL',
    'DATA_QUALITY',
    4.0,
    'Truy van phat hien trung lap va gia tri NULL',
    'draft'
),
(
    '30000000-0000-0000-0000-000000000003',
    '10000000-0000-0000-0000-000000000001',
    'ACT_VIZ_01',
    'Truc quan hoa du lieu: Chon va dung bieu do',
    'DATA_VIZ',
    4.0,
    'Bieu do xu huong va so sanh kem nhan don vi',
    'draft'
),
(
    '30000000-0000-0000-0000-000000000004',
    '10000000-0000-0000-0000-000000000001',
    'ACT_COMM_01',
    'Viet nhan xet & trinh bay insight tu so lieu',
    'WRITTEN_EXPLANATION',
    4.0,
    'Bao cao ngan duoi 120 tu cho quan ly',
    'draft'
),
(
    '30000000-0000-0000-0000-000000000005',
    '10000000-0000-0000-0000-000000000001',
    'ACT_INT_01',
    'Bai tap tich hop du an ban le (Capstone mini)',
    'SQL',
    8.0,
    'Dashboard bao cao tong hop du lieu sach va ket luan',
    'draft'
),
(
    '30000000-0000-0000-0000-000000000006',
    '10000000-0000-0000-0000-000000000001',
    'ACT_REASSESS_01',
    'Danh gia lai nang luc (Bien the B)',
    'SQL',
    4.0,
    'Bai lam bien the tuong duong theo cung rubric',
    'draft'
)
ON CONFLICT (career_version_id, activity_code) DO NOTHING;

-- 7. Activity Prerequisites (Set up while status is 'draft')
INSERT INTO activity_prerequisites (activity_id, prerequisite_activity_id)
VALUES
(
    '30000000-0000-0000-0000-000000000002',
    '30000000-0000-0000-0000-000000000001'
),
(
    '30000000-0000-0000-0000-000000000005',
    '30000000-0000-0000-0000-000000000002'
),
(
    '30000000-0000-0000-0000-000000000005',
    '30000000-0000-0000-0000-000000000003'
),
(
    '30000000-0000-0000-0000-000000000006',
    '30000000-0000-0000-0000-000000000005'
)
ON CONFLICT (activity_id, prerequisite_activity_id) DO NOTHING;

-- Now publish all activity_catalog rows
UPDATE activity_catalog 
SET status = 'published' 
WHERE career_version_id = '10000000-0000-0000-0000-000000000001';

-- 8. Third-party Learning Resources
INSERT INTO learning_resources (resource_id, title, provider, resource_url, skill_code, estimated_hours, approved_by, status)
VALUES
(
    '40000000-0000-0000-0000-000000000001',
    'SQL for Data Analysis',
    'Mode Analytics',
    'https://mode.com/sql-tutorial/',
    'SQL',
    6.0,
    NULL,
    'draft'
),
(
    '40000000-0000-0000-0000-000000000002',
    'Data Cleaning with Python & Pandas',
    'Kaggle Learn',
    'https://www.kaggle.com/learn/data-cleaning',
    'DATA_QUALITY',
    4.0,
    NULL,
    'draft'
),
(
    '40000000-0000-0000-0000-000000000003',
    'Storytelling with Data',
    'Cole Nussbaumer Knaflic',
    'https://www.storytellingwithdata.com/chart-guide',
    'DATA_VIZ',
    3.0,
    NULL,
    'draft'
)
ON CONFLICT (resource_url) DO NOTHING;

-- Map resources to activities
INSERT INTO activity_resources (activity_id, resource_id)
VALUES
('30000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000001'),
('30000000-0000-0000-0000-000000000002', '40000000-0000-0000-0000-000000000002'),
('30000000-0000-0000-0000-000000000003', '40000000-0000-0000-0000-000000000003')
ON CONFLICT DO NOTHING;

-- Publish resources
UPDATE learning_resources 
SET status = 'published' 
WHERE approved_by = '00000000-0000-0000-0000-000000000001';

-- Retention function moved to 007_retention.sql.

COMMIT;