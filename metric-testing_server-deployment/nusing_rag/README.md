# Project Code

本目录包含当前重构后的后端、静态前端、测试与报告输出。

## 目录说明

- `backend/`: FastAPI 后端工程
- `frontend/`: 原生 HTML/CSS/JavaScript 静态前端
- `tests/`: 模块测试与接口测试
- `reports/latest/`: 最新测试报告输出

## 启动后端

在 `project_code/backend` 下启动 FastAPI 服务，例如：

```bash
uvicorn app.main:app --reload
```

默认访问地址：

- API 根路径：`http://127.0.0.1:8000/api/v1`
- 前端首页：`http://127.0.0.1:8000/`

## 前端说明

当前前端不依赖 `Node.js`、`npm` 或任何构建工具。

静态前端文件：

- `frontend/index.html`
- `frontend/styles.css`
- `frontend/app.js`

后端已经在 [main.py](file:///c:/Users/22575/Desktop/fu/rag_new/project_code/backend/app/main.py) 中通过 `StaticFiles` 挂载该目录，因此启动后端后即可直接访问首页。

## 测试

阶段 E 接口联调测试：

```bash
pytest c:\Users\22575\Desktop\fu\rag_new\project_code\tests\api\test_phase_e_integration.py -q
```

运行全部测试：

```bash
python c:\Users\22575\Desktop\fu\rag_new\project_code\tests\run_all.py
```

## 当前前端能力

- 服务菜单按钮入口
- 自由输入意图识别
- 规则评估 WebSocket 交互
- 护理咨询 WebSocket 流式回答
- 产品分类浏览、分页与详情查看
- 设备跟进与库存结果展示
