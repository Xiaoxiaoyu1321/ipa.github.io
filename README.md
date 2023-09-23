# xyiPA

## 安装
此项目基于 [PDM](https://github.com/pdm-project/pdm) 进行包管理。构建此项目之前，请安装 PDM。

安装完成后，执行以下命令安装依赖：
```bash
pdm install
```

本地调试：
```bash
pdm run app start
```

构建：
```bash
pdm run app build
```

构建结果输出于 `dist` 目录下。

## 添加应用与图标
配置文件位于 `data/manifest.json`，请根据实际情况进行修改。

请确保相关图标以 `<bundle_id>.png` 的形式放置在 `data/icons` 目录下。

## 自动化部署
此项目支持基于 GitHub Actions 自动化部署。请确保您已启用 GitHub Actions，在项目被推送到 GitHub 时，将自动触发构建与部署。

部署结果输出于 `static-pages` 分支下。您可以使用 GitHub Pages、Cloudflare Pages 或 Vercel 等服务进行托管。
