-- MomFit 관리자 대시보드(admin-01~04): 운영 DB 반영 SQL
-- 코드를 배포하기 전에 먼저 실행한다. (새 코드가 users.role을 읽으므로 없으면 500이 난다)
-- 실행 전에 운영 DB를 백업하고, 이미 적용된 DB에는 재실행하지 않는다.
--
-- [선행 조건] users.id가 BIGINT여야 한다. (#22 유저·인증 id BIGINT 변경의 수동 ALTER를 먼저 적용)
--   확인: SHOW COLUMNS FROM users LIKE 'id';   -- Type이 bigint 여야 함
--   daily_visits.user_id는 users.id를 참조하는 FK(BIGINT)라서, users.id가 INT인 채로 배포하면
--   서버 시작 때 create_all의 FK 생성이 타입 불일치로 실패한다.
--
-- daily_visits, admin_audit_logs 테이블은 서버가 시작할 때 create_all이 만들므로 이 파일에 없다.

ALTER TABLE users
    ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user';

-- 관리자 지정 (id는 실제 관리자 계정으로 바꾼다)
-- UPDATE users SET role = 'admin' WHERE id = 1;
