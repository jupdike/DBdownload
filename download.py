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

from dropbox_content_hasher import *

if sys.version.startswith('2'):
    input = raw_input  # noqa: E501,F821; pylint: disable=redefined-builtin,undefined-variable,useless-suppression

import dropbox
#   pip install dropbox
#
# Make sure it is a version that supports API v2 access
# API v1 is no more.


# OAuth2 access token.  TODO: login etc.
TOKEN = None #open('dropbox-acctok.txt').read().strip()

parser = argparse.ArgumentParser(description='Sync a <folder in Dropbox> to a <local folder>')
parser.add_argument('folder', nargs='?', default='BOGUS-folder_NAME',
                    help='Folder name in your Dropbox')
parser.add_argument('rootdir', nargs='?', default='~/BOGUS-folder-ALSO',
                    help='Local directory to make the same as <folder>')
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
        #print('res.entries.length:', count)
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
    #print(len(data), 'bytes')   #; md:', md)
    return data

def download_path(dbx, path):
    """Download a file.

    Return the bytes of the file, or None if it doesn't exist.
    """
    if len(path) < 1:
        return None
    if path[0] != '/':
        path = '/' + path
    with stopwatch('download'):
        try:
            md, res = dbx.files_download(path)
        except dropbox.exceptions.HttpError as err:
            print('*** HTTP error', err)
            return None
    data = res.content
    #print(len(data), 'bytes')   #; md:', md)
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
    #print('mkdir -p '+path)
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

def get_remote_tree(dbx, folder, subfolder):
    bag = {}
    _get_remote_tree_inner(dbx, folder, subfolder, bag)
    return bag

def path_combine(path1, path2):
    path = '%s/%s' % (path1, path2)
    path = path.replace(os.path.sep, '/')
    while '//' in path:
        path = path.replace('//', '/')
    return path

def get_local_content_hash(fname):
    hasher = DropboxContentHasher()
    with open(fname, 'rb') as f:
        while True:
            chunk = f.read(128*1024)  # or whatever chunk size you want
            if len(chunk) == 0:
                break
            hasher.update(chunk)
    return hasher.hexdigest()

def _get_remote_tree_inner(dbx, folder, subfolder, bag):
    listing = list_folder(dbx, folder, subfolder)
    for name, md in listing.items():
        if type(md) is dropbox.files.FolderMetadata:
            #print('-- Folder')
            path = '%s/%s' % (subfolder.replace(os.path.sep, '/'), name)
            while '//' in path:
                path = path.replace('//', '/')
            _get_remote_tree_inner(dbx, folder, path, bag)
        if type(md) is dropbox.files.FileMetadata:
            path = '%s/%s' % (subfolder.replace(os.path.sep, '/'), name)
            while '//' in path:
                path = path.replace('//', '/')
            # track input paths
            bag[path] = md

def get_local_tree(rootdir, folder):
    ret = set()
    #top = path_combine(rootdir, folder)
    top = rootdir
    #print('---\ntop:', top)
    for dn, dirs, files in os.walk(top):
        subfolder = dn[len(rootdir):].strip(os.path.sep)
        #print('subfolder:', subfolder)
        for name in files:
            fullname = os.path.join(dn, name)
            if not isinstance(name, six.text_type):
                name = name.decode('utf-8')
            name = unicodedata.normalize('NFC', name)
            if name.startswith('.'):
                print('Skipping dot file:', name)
            elif name.startswith('@') or name.endswith('~'):
                print('Skipping temporary file:', name)
            else:
                #sub2 = subfolder[len(folder):]
                fname = path_combine(subfolder, name)
                if not fname.startswith('/'):
                    fname = '/' + fname
                #print('   ', fname)
                ret.add(fname)
    return ret

def ensure_folder_for_file(fname):
    direc = os.path.dirname(fname)
    #print('direc:', direc)
    mkdir_p(direc)

# folder is remote folder name
# rootdir is local folder to write into (with relatives path relative to this 'rootdir')
def smart_download(dbx, folder, rootdir):
    any_change = False

    subfolder = ''
    remote_map = get_remote_tree(dbx, folder, subfolder)
    #print('remote:', remote_map.keys())
    local_set  = get_local_tree(rootdir, folder)
    #print('local:', local_set)
    # remove excess files
    for local in local_set:
        if not remote_map.has_key(local):
            fname = path_combine(rootdir, local)
            print('NEED TO DELETE:', fname)
            os.remove(fname)
            any_change = True
    # TODO remove empty folders that are no longer part of the paths of any remote files
    # ...

    # look for files that are the wrong file size, or if the same, the wrong content hash
    needed = set()
    for name, md in remote_map.items():
        #print('---')
        fname = path_combine(rootdir, name)
        if not os.path.isfile(fname):
            needed.add(name) # not with local path
            #print('(does not exist) NEED TO DOWNLOAD:', fname)
            any_change = True
            continue
        #print('file already exists:', fname)
        if os.path.getsize(fname) != md.size:
            needed.add(name) # not with local path
            #print('(file is the wrong size) NEED TO DOWNLOAD:', fname)
            any_change = True
            continue
        if get_local_content_hash(fname) != md.content_hash:
            needed.add(name) # not with local path
            #print('(file has wrong contents) NEED TO DOWNLOAD:', fname)
            any_change = True
            continue
        #print('file is up-to-date:', fname)
    #print('needed:', needed)

    # actually download anything that is left...
    for name in needed:
        fname = path_combine(rootdir, name)
        md = remote_map[name]
        remotepath = path_combine(folder, name)
        bites = download_path(dbx, remotepath)
        print('Downloaded', len(bites), 'of', remotepath, 'to', fname)
        # write out <bites> to file <path>
        ensure_folder_for_file(fname)
        open(fname, 'wb').write(bites)

    if any_change:
        print('Some files were changed.')
    else:
        print('Nothing changed. Already up-to-date.')

    return any_change

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

    any_change = smart_download(dbx, folder, rootdir)
    if any_change:
        exit(0) # means    python download.py x y z && echo 'Do more stuff'  --> prints out "Do more stuff"
    else:
        exit(1) # means    python download.py x y z && echo 'Do more stuff'  --> right-hand side of && is not executed

if __name__ == '__main__':
    main()
