# -*- coding: utf-8 -*-
"""Cullinan FileInfo

File info container for handling uploaded files.

Author: Cullinan
"""

import os
import mimetypes
from typing import Optional, List, BinaryIO
from io import BytesIO


class FileInfo:
    """File info container

    Encapsulates metadata and content of uploaded files, providing convenient access methods.

    Attributes:
        filename: Original filename
        content_type: MIME type
        body: File content (bytes)
        size: File size (bytes)

    Example:
        @post_api(url='/upload')
        async def upload(self, avatar: File()):
            # avatar is a FileInfo instance
            print(f"Filename: {avatar.filename}")
            print(f"Size: {avatar.size} bytes")
            print(f"Type: {avatar.content_type}")

            # Save file
            avatar.save('/path/to/uploads/')

            # Or read content
            content = avatar.read()
    """

    __slots__ = ('_filename', '_content_type', '_body', '_field_name')

    def __init__(
        self,
        filename: str,
        body: bytes,
        content_type: str = None,
        field_name: str = None,
    ):
        """Initialize file info

        Args:
            filename: Original filename
            body: File content
            content_type: MIME type, auto-detected if not provided
            field_name: Form field name
        """
        self._filename = filename
        self._body = body if body is not None else b''
        self._content_type = content_type or self._detect_content_type(filename)
        self._field_name = field_name

    @property
    def filename(self) -> str:
        """Original filename"""
        return self._filename

    @property
    def content_type(self) -> str:
        """MIME type"""
        return self._content_type

    @property
    def body(self) -> bytes:
        """File content (bytes)"""
        return self._body

    @property
    def size(self) -> int:
        """File size (bytes)"""
        return len(self._body)

    @property
    def field_name(self) -> Optional[str]:
        """Form field name"""
        return self._field_name

    @property
    def extension(self) -> str:
        """File extension (without dot)"""
        _, ext = os.path.splitext(self._filename)
        return ext[1:] if ext else ''

    @property
    def basename(self) -> str:
        """File base name (without extension)"""
        name, _ = os.path.splitext(self._filename)
        return name

    def read(self) -> bytes:
        """Read file content

        Returns:
            File content (bytes)
        """
        return self._body

    def read_text(self, encoding: str = 'utf-8') -> str:
        """Read file content as text

        Args:
            encoding: Text encoding

        Returns:
            File content (str)
        """
        return self._body.decode(encoding)

    def stream(self) -> BinaryIO:
        """Get file stream

        Returns:
            BytesIO object
        """
        return BytesIO(self._body)

    def save(self, path: str, filename: str = None) -> str:
        """Save file to disk

        Args:
            path: Save directory or full path
            filename: Custom filename, uses original filename if not provided

        Returns:
            Full saved path
        """
        if os.path.isdir(path):
            # If directory, join with filename
            save_name = filename or self._filename
            full_path = os.path.join(path, save_name)
        else:
            # If full path
            full_path = path

        # Ensure directory exists
        dir_path = os.path.dirname(full_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path)

        with open(full_path, 'wb') as f:
            f.write(self._body)

        return full_path

    def is_image(self) -> bool:
        """Check if image file"""
        return self._content_type.startswith('image/')

    def is_video(self) -> bool:
        """Check if video file"""
        return self._content_type.startswith('video/')

    def is_audio(self) -> bool:
        """Check if audio file"""
        return self._content_type.startswith('audio/')

    def is_text(self) -> bool:
        """Check if text file"""
        return self._content_type.startswith('text/')

    def is_pdf(self) -> bool:
        """Check if PDF file"""
        return self._content_type == 'application/pdf'

    def match_type(self, pattern: str) -> bool:
        """Check if MIME type matches pattern

        Args:
            pattern: MIME type pattern, supports wildcards like 'image/*'

        Returns:
            Whether it matches
        """
        if pattern == '*/*' or pattern == '*':
            return True

        if pattern.endswith('/*'):
            # Wildcard match, e.g. image/*
            prefix = pattern[:-1]  # 'image/'
            return self._content_type.startswith(prefix)

        return self._content_type == pattern

    @staticmethod
    def _detect_content_type(filename: str) -> str:
        """Detect MIME type from filename

        Args:
            filename: Filename

        Returns:
            MIME type
        """
        content_type, _ = mimetypes.guess_type(filename)
        return content_type or 'application/octet-stream'

    @classmethod
    def from_upload_payload(cls, file_obj) -> 'FileInfo':
        """Create FileInfo from a transport layer upload object.

        Args:
            file_obj: File upload object or dict provided by the specific web backend

        Returns:
            FileInfo instance
        """
        return cls(
            filename=file_obj.get('filename', 'unknown'),
            body=file_obj.get('body', b''),
            content_type=file_obj.get('content_type'),
            field_name=file_obj.get('field_name'),
        )

    def __repr__(self) -> str:
        return f"FileInfo(filename={self._filename!r}, size={self.size}, type={self._content_type!r})"

    def __str__(self) -> str:
        return f"{self._filename} ({self.size} bytes, {self._content_type})"

    def __len__(self) -> int:
        return self.size

    def __bool__(self) -> bool:
        return self.size > 0


class FileList:
    """File list container

    For handling multi-file upload scenarios.

    Example:
        @post_api(url='/upload-multiple')
        async def upload(self, files: File(multiple=True)):
            for f in files:
                print(f.filename)
            print(f"Total: {len(files)} files")
    """

    __slots__ = ('_files',)

    def __init__(self, files: List[FileInfo] = None):
        """Initialize file list

        Args:
            files: List of FileInfo
        """
        self._files = files or []

    def __iter__(self):
        return iter(self._files)

    def __len__(self) -> int:
        return len(self._files)

    def __getitem__(self, index: int) -> FileInfo:
        return self._files[index]

    def __bool__(self) -> bool:
        return len(self._files) > 0

    @property
    def count(self) -> int:
        """File count"""
        return len(self._files)

    @property
    def total_size(self) -> int:
        """Total file size"""
        return sum(f.size for f in self._files)

    @property
    def filenames(self) -> List[str]:
        """All filenames"""
        return [f.filename for f in self._files]

    def first(self) -> Optional[FileInfo]:
        """Get first file"""
        return self._files[0] if self._files else None

    def last(self) -> Optional[FileInfo]:
        """Get last file"""
        return self._files[-1] if self._files else None

    def filter_by_type(self, pattern: str) -> 'FileList':
        """Filter files by MIME type

        Args:
            pattern: MIME type pattern

        Returns:
            Filtered FileList
        """
        return FileList([f for f in self._files if f.match_type(pattern)])

    def save_all(self, directory: str) -> List[str]:
        """Save all files to directory

        Args:
            directory: Save directory

        Returns:
            List of saved file paths
        """
        paths = []
        for f in self._files:
            path = f.save(directory)
            paths.append(path)
        return paths

    def __repr__(self) -> str:
        return f"FileList({len(self._files)} files, total {self.total_size} bytes)"
