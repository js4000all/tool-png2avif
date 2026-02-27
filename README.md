# tool-png2avif

PNG画像をAVIF形式へ一括変換するシンプルなCLIツールです。
指定ディレクトリ以下を再帰的に探索し、PNGをAVIFへ変換します。

変換成功後、元のPNGは削除されます（dryrunモードあり）。

---

## Quick Start

```bash
git clone https://github.com/js4000all/tool-png2avif.git
cd tool-png2avif
pip install -r requirements.txt
python png2avif.py imagedir
```

これだけで `imagedir` 以下のPNGがAVIFに変換されます。

---

## Features

* ディレクトリを再帰的に走査
* PNG → AVIF へ変換
* 画質をオプションで指定可能
* dryrunモード対応（変換・削除ログのみ表示）
* 単一PNGファイル指定も可能

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

pip install -r requirements.txt
```

---

### Option B: グローバル環境にインストール

```bash
pip install -r requirements.txt
```

---

## Usage

```
python png2avif.py [--dryrun] [--quality QUALITY] <target_path>
```

### Arguments

| オプション       | 説明                       |
| ----------- | ------------------------ |
| target_path | 変換対象ディレクトリまたはPNGファイル（必須） |
| --quality   | AVIF品質（0–100, デフォルト: 80） |
| --dryrun    | 変換削除を実行せず、対象ファイルのログのみ出力          |

---

## Examples

### 通常実行（デフォルト quality=80）

```
python png2avif.py imagedir
```

### qualityを指定

```
python png2avif.py --quality 70 imagedir
```

### dryrun

```
python png2avif.py --dryrun imagedir
```

### dryrun + quality指定

```
python png2avif.py --dryrun --quality 70 imagedir
```

---

## Output Example

```
converted: imagedir/sample.png -> imagedir/sample.avif
removed: imagedir/sample.png
```

---

## Notes

* 既に同名の `.avif` ファイルが存在する場合は上書きされます。
* 透過PNG（RGBA）にも対応しています。
* 変換成功時のみ元PNGを削除します。
* `--dryrun` を使用すると、実際のファイル変更は行われません。
* 画質を下げるとファイルサイズは小さくなりますが、画質も低下します。

---

## License

MIT License
