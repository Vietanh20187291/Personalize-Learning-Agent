# Production Scaling Blueprint

Tai lieu nay mo ta cach dua he thong len mo hinh production-ready de phuc vu muc tieu khoang 1000 sinh vien active dong thoi ma khong sap backend.

## 1. Cac thay doi da duoc dua vao code

- DB pooling cho PostgreSQL thong qua `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`, `DATABASE_POOL_TIMEOUT_SECONDS`, `DATABASE_POOL_RECYCLE_SECONDS`.
- Conversation memory cua Nova co the chuyen tu in-memory sang Redis bang `REDIS_URL`.
- Bo health/readiness rieng tai:
  - `GET /api/ops/health`
  - `GET /api/ops/readiness`
- Gunicorn production config co worker/process/thread rotation.
- Upload storage duoc dua ve `TEMP_UPLOADS_DIR` de de gan shared volume giua nhieu backend node.

## 2. Kien truc production khuyen nghi

```text
Client
  -> Nginx / Load Balancer
      -> Frontend replicas (2+)
      -> Backend replicas (2-4)
            -> PostgreSQL
            -> Redis
            -> Shared temp_uploads volume
            -> Vector store
```

## 3. Thanh phan bat buoc de scale ngang

### PostgreSQL thay cho SQLite

SQLite hop cho dev va test, nhung khong phu hop khi nhieu request ghi dong thoi. Production can chuyen sang PostgreSQL.

### Redis cho state chia se

Teacher agent truoc day luu context trong RAM cua process. Khi co nhieu backend instance sau load balancer, state nay se bi lech giua cac node. Redis giai quyet van de do bang cach luu bo nho hoi thoai tap trung.

### Shared storage cho tai lieu va OCR artifacts

Neu moi backend node co file system rieng, preview tai lieu va ket qua OCR se bi "not found" khi request vao node khac. Can mount chung `temp_uploads` tren tat ca backend replica (NFS, EFS, Azure Files, shared PVC, hoac object storage gateway).

### Health/readiness cho load balancer

Load balancer chi nen route request toi node dat `GET /api/ops/readiness` = `200`.

## 4. Khuyen nghi thong so ban dau cho 1000 active users

- Backend replicas: 2-4
- Gunicorn workers moi replica: 4
- Threads moi worker: 2
- PostgreSQL pool size moi replica: 20-30
- Redis: 1 node + persistence AOF
- Frontend replicas: 2
- Nginx upstream policy: `least_conn`

Tong cong 2 backend replicas x 4 workers = 8 backend workers. Day la diem khoi dau hop ly de test tai va tinh tiep.

## 5. Nhin thang vao cac diem nghen lon nhat con lai

### LLM latency

Neu 1000 sinh vien dong thoi deu chat AI, diem nghen lon nhat thuong khong nam o FastAPI ma nam o thoi gian response cua provider LLM. Can:

- dat timeout chat ro rang
- tach request nang sang background job neu phu hop
- cache cac response mau / examples / summaries
- gioi han so request AI dong thoi o gateway neu can

### OCR va sinh de la job nang

OCR PDF nhieu trang va sinh de Word la CPU-bound / IO-bound. Khong nen de nhung job nay can tranh worker chat chinh trong gio cao diem. Khuyen nghi:

- tach sang worker queue rieng (Celery/RQ/Dramatiq)
- backend API chi nhan job va tra job id
- frontend poll trang thai hoac nhan callback

### Chroma local

Voi load lon va nhieu node, vector store local tren volume chung chua phai lua chon ly tuong. Huong nang cap chuyen nghiep hon:

- Qdrant
- Milvus
- PostgreSQL + pgvector

Trong giai doan chuyen tiep, co the van doc tu Chroma local, nhung nen gioi han ingestion trong khung gio cao diem.

## 6. Cach chay bo deploy mau

Tu thu muc `deploy/production`:

```bash
docker compose -f docker-compose.prod.yml up --build
```

Sau khi len:

- Frontend + API vao qua `http://localhost`
- Health chi tiet: `http://localhost/api/ops/health`
- Readiness cho load balancer: `http://localhost/api/ops/readiness`

## 7. Lo trinh nang cap tiep theo neu muon "enterprise-grade"

1. Dua OCR va exam generation sang queue worker rieng.
2. Dua vector store sang dich vu chuyen dung thay vi local Chroma.
3. Dua file storage sang S3/MinIO thay vi shared disk.
4. Them metrics Prometheus + Grafana.
5. Them tracing (OpenTelemetry).
6. Them rate limiting va circuit breaker cho LLM endpoints.
7. Deploy bang Kubernetes / ECS thay vi docker compose khi can auto-scaling that su.
