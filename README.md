# tool-png2avif

PNG画像をAVIF形式へ一括変換するシンプルなCLIツールです。
指定ディレクトリ以下を再帰的に探索し、PNGをAVIFへ変換します。

変換成功後、元のPNGは削除されます（dryrunモードあり）。

---

## Quick Start

```bash
git clone https://github.com/js4000all/tool-png2avif.git
cd tool-png2avif
pip install .
png2avif imagedir
```

これだけで `imagedir` 以下のPNGがAVIFに変換されます。

---

## Features

* ディレクトリを再帰的に走査
* PNG → AVIF へ変換
* 画質をオプションで指定可能
* dryrunモード対応（副作用のみ無効化）
* verboseモードでファイル単位ログを表示
* 単一PNGファイル指定も可能
* Stable Diffusion WebUI の `parameters` を検出した場合、AVIF の Exif `User Comment` に自動引き継ぎ

---

## Requirements

* Python 3.9+

---

## Installation

### 1. リポジトリを取得

```bash
git clone https://github.com/js4000all/tool-png2avif.git
cd tool-png2avif
```

---

### Option A: 仮想環境を使用する（推奨）

```bash
python -m venv venv
source venv/bin/activate  # macOS / Linux
# または
venv\Scripts\Activate.ps1  # Windows (PowerShell)

pip install .
```

---

### Option B: グローバル環境にインストール

```bash
pip install .
```

---

## Usage

```
png2avif [--verbose] [--dryrun] [--quality QUALITY] [--jobs JOBS] <target_path>
```

### Arguments

| オプション       | 説明                       |
| ----------- | ------------------------ |
| target_path | 変換対象ディレクトリまたはPNGファイル（必須） |
| --quality   | AVIF品質（0–100, デフォルト: 80） |
| --jobs      | 並列ワーカープロセス数（1以上, デフォルト: 1） |
| --verbose   | `converted / removed` のファイル単位ログを出力 |
| --dryrun    | AVIF書き込みとPNG削除を行わない（副作用なし） |

---

## Examples

### 通常実行（デフォルト quality=80）

```
png2avif imagedir
```

### 通常実行（ログあり）

```
png2avif --verbose imagedir
```

### qualityを指定

```
png2avif --quality 70 imagedir
```

### dryrun

```
png2avif --dryrun imagedir
```

### dryrun + verbose

```
png2avif --dryrun --verbose imagedir
```

### dryrun + quality指定

```
png2avif --dryrun --quality 70 imagedir
```

### 4並列で実行

```
png2avif --jobs 4 imagedir
```

### 4並列 + verbose

```
png2avif --jobs 4 --verbose imagedir
```

---

## Output Example (`--verbose` 指定時のみ)

```
converted: imagedir/sample.png -> imagedir/sample.avif
removed: imagedir/sample.png
```

---

## Notes

* 既に同名の `.avif` ファイルが存在する場合は上書きされます。
* 透過PNG（RGBA）にも対応しています。
* 変換成功時のみ元PNGを削除します。
* デフォルトではファイル単位ログは出力されません（`--verbose` 指定時のみ出力）。
* `--dryrun` を使用すると、AVIF書き込みとPNG削除を行いません。
* `--jobs` は 1 以上を指定でき、Converting フェーズは `ProcessPoolExecutor` で実行されます（Scanning は逐次）。
* PNG の `tEXt` / `iTXt` / `zTXt` に `parameters` があれば、AVIF の Exif `User Comment` に格納されます（ASCIIは`ASCII\0\0\0`、非ASCIIは`UNICODE\0` + UTF-16LE）。
* AVIF コンテナの `Handler Description` は `libavif` として埋め込まれ、`exiftool` で確認できます。
* 画質を下げるとファイルサイズは小さくなりますが、画質も低下します。

---

## License

MIT License
