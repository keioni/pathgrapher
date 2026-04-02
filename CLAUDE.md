# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Path Grapher** is a modernized, cross-platform (macOS, Windows, Linux) reimplementation of the Windows tool [DirGraph](https://www.vector.co.jp/soft/win95/util/se030002.html). It visually represents directory disk usage as proportionally-sized blocks in a resizable window.

## Claude Code への指示 (Specification)

* Windows 向けに作られた DirGraph というツールを現代化・マルチOS化したものです
* Python で書かれ、macOS, Windows, Linux などで動作します
* 任意のパスから、サブディレクトリのサイズにあわせてウィンドウの中身を変えます
  * たとえばトップのパスが50GB使っていたとしたら、20GBを使っているパスAは40%の高さのブロックを、30GBを使っているパスBは60%の高さのブロックになります
  * サイズが大きなものブロック下に表示されます。先ほどの例を使うと、パスAが上側、パスBが下側になります
  * ウィンドウサイズは可変です
* ブロックの中には、ディレクトリ名、容量、占有率が描画されます
  * 大きさにあわせてフォントサイズを変え、縦の方が長ければ90度回転して描画します
* ウィンドウの描写と、パスの探索は別プロセス(または別スレッド)で行われます
  * 定期的なタイミングで、取得したパスの情報をウィンドウプロセス・スレッドに送信し、それをもとに更新します

* コード生成にあたっては PEP8 を守ってください
* 変数名は、長くなっても構わないので可能な限り単体で分かるもの使ってください

## Architecture

The application has two concurrent components communicating via a queue or pipe:

1. **Scanner** — walks the filesystem recursively, accumulates directory sizes, and periodically sends snapshots of the current tree to the GUI.
2. **GUI** — renders blocks proportional to each subdirectory's share of the total. Larger directories are placed lower. Block labels (name, size, %) scale with block dimensions and rotate 90° when the block is taller than wide.

The GUI must remain responsive while scanning is in progress, so scanning runs in a separate thread or process.

## Development Setup

Once the project has a `pyproject.toml` or `requirements.txt`, install dependencies with:

```bash
pip install -e ".[dev]"
```

## Commands

Commands will be defined here once build tooling is in place. Expected commands:

```bash
# Run the application
python -m pathgrapher [path]

# Run tests
pytest

# Lint
ruff check .

# Format
ruff format .
```
