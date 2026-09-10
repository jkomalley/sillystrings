# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-09

### Added

- Initial release. Extracts printable character sequences from binary files,
  reimplementing the Unix `strings` utility in pure Python with no runtime
  dependencies.
- Four encodings via `-e`: 7-bit ASCII (`s`, the default), 8-bit extended
  ASCII (`S`), and UTF-16 little- and big-endian (`l` and `b`).
- `-n` to set the minimum string length, `-t` to print byte offsets in
  decimal, octal or hexadecimal, `-w` to treat all whitespace as part of a
  string, and `-f` to print the filename before each match.
- Reads from stdin when given no file arguments or a `-` argument, and accepts
  multiple files in one invocation.

[Unreleased]: https://github.com/jkomalley/sillystrings/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jkomalley/sillystrings/releases/tag/v0.1.0
