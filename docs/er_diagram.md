# ER-Diagram for FastDeploy

```mermaid
erDiagram
          USER ||..o{ DEPLOYMENT : starts
          SERVICE ||..o{ DEPLOYMENT : "gets deployed"
          DEPLOYMENT ||..o{ STEP : "consists of"
```
