from __future__ import unicode_literals
import logging
import shutil
import tempfile

from mkdocs.commands.build import build
from mkdocs.config import load_config

log = logging.getLogger(__name__)


def _livereload(host, port, config, builder, site_dir):

    # We are importing here for anyone that has issues with livereload. Even if
    # this fails, the --no-livereload alternative should still work.
    from livereload import Server, watcher
    import os, sys, glob, re

    class MkDocsWatcher(watcher.Watcher):
        def is_glob_changed(self, path, ignore=None):

            if sys.version < (3, 5) and '**' in path:
                start, wildcard = path.split('**', 1)
                for root, dirnames, filenames in os.walk(start):
                    for name in dirnames:
                        for f in glob.glob(os.path.join(root, name, wildcard.strip(os.path.sep))):
                            if self.is_file_changed(f, ignore):
                                return True

                            # Check sub-pages
                            with open(f) as fid:
                                content = fid.read()
                                for match in re.finditer(r'\{!(.*?)!\}', content):
                                    subpage = match.group(1)
                                    if os.path.exists(subpage):
                                        if self.is_file_changed(subpage, ignore):
                                            return True
                return False
            else:
                return super(MkDocsWatcher, self).is_glob_changed(path, ignore)


    watcher = MkDocsWatcher()
    server = Server(None, watcher)

    # Watch the documentation files, the config file and the theme files.
    server.watch(os.path.join(config['docs_dir'], '**', '*.md'), builder)
    server.watch(config['config_file_path'], builder)

    for d in config['theme_dir']:
        server.watch(d, builder)

    for d in config['watch_dirs']:
        server.watch(d, builder)

    server.serve(root=site_dir, host=host, port=int(port), restart_delay=0)

def _static_server(host, port, site_dir):

    # Importing here to separate the code paths from the --livereload
    # alternative.
    from tornado import ioloop
    from tornado import web

    application = web.Application([
        (r"/(.*)", web.StaticFileHandler, {
            "path": site_dir,
            "default_filename": "index.html"
        }),
    ])
    application.listen(port=int(port), address=host)

    log.info('Running at: http://%s:%s/', host, port)
    log.info('Hold ctrl+c to quit.')
    try:
        ioloop.IOLoop.instance().start()
    except KeyboardInterrupt:
        log.info('Stopping server...')


def serve(config_file=None, dev_addr=None, strict=None, theme=None,
          theme_dir=None, livereload=True):
    """
    Start the MkDocs development server

    By default it will serve the documentation on http://localhost:8000/ andcon
    it will rebuild the documentation and refresh the page automatically
    whenever a file is edited.
    """
    # Create a temporary build directory, and set some options to serve it
    tempdir = tempfile.mkdtemp()


    class Builder():
        def __init__(self):
            log.info("Building documentation...")

            # Configuration
            self.config = load_config(
                config_file=config_file,
                dev_addr=dev_addr,
                strict=strict,
                theme=theme,
                theme_dir=theme_dir,
            )
            self.config['site_dir'] = tempdir

            # A cache for SiteNavigation object
            self._site_navigation = None

            # Perform initial build
            self.__call__()

        def __call__(self):

            if self._site_navigation:
                self._site_navigation = build(self.config, live_server=True, clean_site_dir=False, cache=self._site_navigation)
            else:
                self._site_navigation = build(self.config, live_server=True, clean_site_dir=False)


    # Perform the initial build
    builder = Builder()
    host, port = builder.config['dev_addr'].split(':', 1)

    try:
        if livereload:
            _livereload(host, port, builder.config, builder, tempdir)
        else:
            _static_server(host, port, tempdir)
    finally:
        shutil.rmtree(tempdir)
