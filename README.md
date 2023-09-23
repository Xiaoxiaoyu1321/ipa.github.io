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

您也可以指定端口：
```bash
pdm run app start --host 0.0.0.0 --port 8080
```

更多调试参数请使用 `--help` 查看。

## 配置与添加应用图标
配置文件位于 `data/manifest.yaml`，请根据实际情况进行修改。

请确保相关图标以 `<bundle_id>.png` 的形式放置在 `data/icons` 目录下。

## IPA 文件上传到 OSS 的约定
您需要手动将 IPA 文件上传到 OSS。上传路径格式为：
```
<prefix>/package/<bundle_id>/<bundle_id>_<version>.ipa
```

其中：
 - `prefix` 是您在 `data/manifest.yaml` 中配置的 OSS 前缀
 - `bundle_id` IPA 的 Bundle ID，需要与 `plist` 文件中的 `bundle-identifier` 一致
 - `version` 是该软件的版本号，需要与 `plist` 文件中的 `bundle-version` 一致

例如，以以下 OSS 配置为例：
```yaml
# data/manifest.yaml
oss:
  bucket: ipa-guangzhou
  prefix: tfsv1
  endpoint: oss-cn-guangzhou.aliyuncs.com
```

假设您需要上传微信 7.0.2 的 IPA 文件，则您的上传路径为
```
tfsv1/package/com.wechat/com.wechat_7.0.2.ipa
```

如果您已经运行过 `pdm run app upload`，则您可以注意到，上传 IPA 的目录和 `plist` 文件的目录是一致的。

## 构建
您可以使用以下命令构建此项目：
```bash
pdm run app build
```

构建结果输出于 `dist` 目录下。

您可以使用 `--dist` 参数指定构建输出目录：
```bash
pdm run app build --dist /path/to/dist
```

若您想要在构建时清理输出目录，请使用 `--clean` 参数：
```bash
pdm run app build --clean
```

如果使用 GitHub Pages，需要传入 `--cname` 参数来生成 `CNAME` 文件：
```bash
pdm run app build --cname example.com
```

更多构建参数请使用 `--help` 查看。

## 部署到 OSS
为提高访问成功率，最好将 `plist` 文件部署到 OSS 上。您可以使用以下命令将构建结果部署到 OSS（不包含 HTML，仅包含 `plist` 文件）：
```bash
pdm run app upload
```

您需要设置以下环境变量，并确保对应的 RAM 用户具有访问 `manifest.yaml` 中配资的 Bucket 的权限：
 - `OSS_ACCESS_KEY_ID`
 - `OSS_ACCESS_KEY_SECRET`

例如：
```bash
OSS_ACCESS_KEY_ID=xxx OSS_ACCESS_KEY_SECRET=xxx pdm run app upload
```

更多部署参数请使用 `--help` 查看。

## 自动化部署
此项目支持基于 GitHub Actions 自动化部署。请确保您已启用 GitHub Actions，在项目被推送到 GitHub 时，将自动触发构建与部署。

部署结果输出于 `static-pages` 分支下。您可以使用 GitHub Pages、Cloudflare Pages 或 Vercel 等服务进行托管。

此外，新生成的 `plist` 文件也将自动上传到 OSS。为了使此功能正常工作，您需要在 GitHub 项目的 `Settings -> Secrets` 中设置以下环境变量：
 - `OSS_ACCESS_KEY_ID`
 - `OSS_ACCESS_KEY_SECRET`

若您未设置以上环境变量，构建将会失败。

## 提交规范
建议在 Git 提交时，使用以下 Commit Message 格式：
```
<type>(<scope>): <subject>
```

如果修改了多个 scope 的内容，可以省略 `scope`，此时格式如下：
```
<type>: <subject>
```

其中：
 - `type` 为提交类型，可取值如下：
     - `add`: 添加新功能、新的说明、新的文件等
     - `fix`: 修复错误
     - `docs`: 修改文档
     - `refactor`: 重构代码、格式化代码、修改样式
 - `scope` 为提交范围，可取值如下：
     - `app`: 修改生成器 `app.py` 的代码
     - `data`: 新增、删除、修改 IPA 软件包
     - `ci`: 修改 GitHub Actions 或其他 CI/CD 相关内容
     - `pump`: 更新依赖
     - `ui`: 修改网页界面
 - `subject` 为对提交的简短描述，建议使用英文

此外，在 Commit Message 结尾也可添加标识，以达成特定功能：
 - `[skip ci]`: 跳过 CI/CD 流程
 - `[trigger ci]`: 此提交仅为了触发 CI/CD 流程，不包含任何实际内容
