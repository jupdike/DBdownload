"""
Download the contents of a remote folder in your Dropbox to local.
Smart sync it, don't re-download the whole thing every time.
Never uploads data, just makes a read-only copy of the remote.

Based on the example app for Dropbox API v2 'updown.py'
"""

from __future__ import print_function

import argparse
import contextlib
import datetime
import os
import errno
import six
import sys
import time
import unicodedata

if sys.version.startswith('2'):
    input = raw_input  # noqa: E501,F821; pylint: disable=redefined-builtin,undefined-variable,useless-suppression

import dropbox

# USE
# (cd ~/Documents/dev && python DBdownload/download.py Apps/Byword/usa-blogposts ~/Documents/dev/)

# OAuth2 access token.  TODO: login etc.
TOKEN = open('dropbox-acctok.txt').read().strip()

parser = argparse.ArgumentParser(description='Sync ~/Downloads to Dropbox')
parser.add_argument('folder', nargs='?', default='Downloads',
                    help='Folder name in your Dropbox')
parser.add_argument('rootdir', nargs='?', default='~/Downloads',
                    help='Local directory to upload')
parser.add_argument('--token', default=TOKEN,
                    help='Access token '
                    '(see https://www.dropbox.com/developers/apps)')

def list_folder(dbx, folder, subfolder):
    """List a folder.

    Return a dict mapping unicode filenames to
    FileMetadata|FolderMetadata entries.
    """
    path = '/%s/%s' % (folder, subfolder.replace(os.path.sep, '/'))
    while '//' in path:
        path = path.replace('//', '/')
    path = path.rstrip('/')
    try:
        with stopwatch('list_folder'):
            res = dbx.files_list_folder(path)
    except dropbox.exceptions.ApiError as err:
        print('Folder listing failed for', path, '-- assumed empty:', err)
        return {}
    else:
        rv = {}
        count = 0
        for entry in res.entries:
            rv[entry.name] = entry
            count += 1
        print('res.entries.length:', count)
        return rv

def download(dbx, folder, subfolder, name):
    """Download a file.

    Return the bytes of the file, or None if it doesn't exist.
    """
    path = '/%s/%s/%s' % (folder, subfolder.replace(os.path.sep, '/'), name)
    while '//' in path:
        path = path.replace('//', '/')
    with stopwatch('download'):
        try:
            md, res = dbx.files_download(path)
        except dropbox.exceptions.HttpError as err:
            print('*** HTTP error', err)
            return None
    data = res.content
    print(len(data), 'bytes')   #; md:', md)
    return data

@contextlib.contextmanager
def stopwatch(message):
    """Context manager to print how long a block of code took."""
    t0 = time.time()
    try:
        yield
    finally:
        t1 = time.time()
        print('Total elapsed time for %s: %.3f' % (message, t1 - t0))

def mkdir_p(path):
    print('mkdir -p '+path)
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

def download_sub(dbx, folder, subfolder, rootdir):
    listing = list_folder(dbx, folder, subfolder)
    # ensure directory exists
    direc = '%s/%s/%s' % (rootdir, folder, subfolder.replace(os.path.sep, '/'))
    while '//' in direc:
        direc = direc.replace('//', '/')
    mkdir_p(direc)
    for name, md in listing.items():
        if type(md) is dropbox.files.FolderMetadata:
            #print('-- Folder')
            path = '%s/%s' % (subfolder.replace(os.path.sep, '/'), name)
            while '//' in path:
                path = path.replace('//', '/')
            download_sub(dbx, folder, path, rootdir)
        if type(md) is dropbox.files.FileMetadata:
            #print('k,v:', k) #, type(v))
            #print('-- File')
            bites = download(dbx, folder, subfolder, name)
            print('Downloaded', name)
            # write out <bites> to file <path>
            path = '%s/%s/%s/%s' % (rootdir, folder, subfolder.replace(os.path.sep, '/'), name)
            while '//' in path:
                path = path.replace('//', '/')
            print('Outpath:', path)
            open(path, 'wb').write(bites)

def main():
    args = parser.parse_args()
    if not args.token:
        print('--token is mandatory')
        sys.exit(2)
    folder = args.folder
    rootdir = os.path.expanduser(args.rootdir)
    print('Dropbox folder name:', folder)
    print('Local directory:', rootdir)
    if not os.path.exists(rootdir):
        print(rootdir, 'does not exist on your filesystem')
        sys.exit(1)
    elif not os.path.isdir(rootdir):
        print(rootdir, 'is not a folder on your filesystem')
        sys.exit(1)
    
    # Ready
    dbx = dropbox.Dropbox(args.token)

    subfolder = ''
    download_sub(dbx, folder, subfolder, rootdir)

if __name__ == '__main__':
    main()
