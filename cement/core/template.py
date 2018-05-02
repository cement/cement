"""Cement core template module."""

import os
import sys
import pkgutil
import re
import shutil
from abc import abstractmethod
from ..core import exc
from ..core.handler import Handler
from ..utils.misc import minimal_logger
from ..utils import fs

LOG = minimal_logger(__name__)


class TemplateHandlerBase(Handler):

    """
    This class defines the Template Handler Interface.  Classes that
    implement this interface must provide the methods and attributes defined
    below.

    Usage:

        .. code-block:: python

            from cement.core.template import TemplateHandlerBase

            class MyTemplateHandler(TemplateHandlerBase):
                class Meta:
                    label = 'my_template_handler'
                ...

    """

    class Meta:

        """Handler meta-data."""

        #: The string identifier of the interface
        interface = 'template'

    @abstractmethod
    def render(self, content, data):
        """
        Render ``content`` as a template using the ``data`` dict.

        Args:
            content (str): The content to be rendered as a template.
            data (dict): The data dictionary to render with template.

        Returns:
            str: The rendered template string.

        """
        pass

    @abstractmethod
    def copy(self, src, dest, data):
        """
        Render the ``src`` directory path, and copy to ``dest``.  This method
        must render directory and file **names** as template content, as well
        as the contents of files.

        Args:
            src (str): The source template directory path.
            dest (str): The destination directory path.
            data (dict): The data dictionary to render with template.
        Returns: None
        """
        pass

    @abstractmethod
    def load(self, path):
        """
        Loads a template file first from ``self.app._meta.template_dirs`` and
        secondly from ``self.app._meta.template_module``.  The
        ``template_dirs`` have presedence.

        Args:
            path (str): The secondary path of the template **after**
                either ``template_module`` or ``template_dirs`` prefix (set via
                ``App.Meta``)

        Returns:
            tuple: The content of the template (``str``), the type of template
            (``str``: ``directory``, or ``module``), and the path (``str``) of
            the directory or module)

        Raises:
            cement.core.exc.FrameworkError: If the template does not exist in
                either the ``template_module`` or ``template_dirs``.
        """
        pass


class TemplateHandler(TemplateHandlerBase):
    """
    Base class that all template implementations should sub-class from.
    Keyword arguments passed to this class will override meta-data options.
    """

    class Meta:
        #: Unique identifier (str), used internally.
        label = None

        #: The interface that this handler implements.
        interface = 'template'

        #: List of file patterns to exclude (copy but not render as template)
        exclude = [
            '^(.*)\.png$',
            '^(.*)\.jpg$',
            '^(.*)\.jpeg$',
            '^(.*)\.gif$',
            '^(.*)\.exe$',
            '^(.*)\.bin$',
            '^(.*)\.zip$',
            '^(.*)\.tar$',
            '^(.*)\.tar.gz$',
            '^(.*)\.tgz$',
            '^(.*)\.gz$',
            '^(.*)\.pyo$',
            '^(.*)\.pyc$',
        ]

        #: List of file patterns to ignore completely (not copy at all)
        ignore = None

    def __init__(self, *args, **kwargs):
        super(TemplateHandler, self).__init__(*args, **kwargs)
        if self._meta.ignore is None:
            self._meta.ignore = []
        if self._meta.exclude is None:
            self._meta.exclude = []

    def render(self, content, data):
        """
        Render ``content`` as template using using the ``data`` dictionary.

        Args:
            content (str): The content to render.
            data (dict): The data dictionary to interpolate in the template.

        Returns:
            str: The rendered content.
        """

        # must be provided by a subclass
        raise NotImplemented

    def copy(self, src, dest, data, force=False, exclude=None, ignore=None):
        """
        Render ``src`` directory as template, including directory and file
        names, and copy to ``dest`` directory.

        Args:
            src (str): The source directory path.
            dest (str): The destination directory path.
            data (dict): The data dictionary to interpolate in the template.
            force (bool): Whether to overwrite existing files.
            exclude (list): List of regular expressions to match files that
                should only be copied, and not rendered as template.
            ignore (list): List of regular expressions to match files that
                should be completely ignored and not copied at all.

        Returns:
            bool: Returns ``True`` if the copy completed successfully.

        Raises:
            AssertionError: If the ``src`` template directory path does not
                exists, and when a ``dest`` file already exists and
                ``force is not True``.
        """

        dest = fs.abspath(dest)
        src = fs.abspath(src)
        if exclude is None:
            exclude = []
        if ignore is None:
            ignore = []

        assert os.path.exists(src), "Source path %s does not exist!" % src

        if not os.path.exists(dest):
            os.makedirs(dest)

        self.app.log.debug('Copying source template %s -> %s' % (src, dest))

        # here's the fun
        for cur_dir, sub_dirs, files in os.walk(src):
            if cur_dir == '.':
                continue

            # don't render the source base dir (because we are telling it
            # where to go as `dest`)
            if cur_dir == src:
                cur_dir_dest = dest
            else:
                # render the cur dir
                self.app.log.debug('rendering template %s' % cur_dir)
                cur_dir_stub = re.sub(src,
                                      '',
                                      self.render(cur_dir, data))
                cur_dir_stub = cur_dir_stub.lstrip('/')
                cur_dir_stub = cur_dir_stub.lstrip('\\')
                cur_dir_dest = os.path.join(dest, cur_dir_stub)

            # render sub-dirs
            for sub_dir in sub_dirs:
                self.app.log.debug('rendering template %s' % sub_dir)
                new_sub_dir = re.sub(src,
                                     '',
                                     self.render(sub_dir, data))
                sub_dir_dest = os.path.join(cur_dir_dest, new_sub_dir)

                if not os.path.exists(sub_dir_dest):
                    self.app.log.debug('Creating sub-directory %s' %
                                       sub_dir_dest)
                    os.makedirs(sub_dir_dest)

            for _file in files:
                self.app.log.debug('rendering template %s' % _file)
                new_file = re.sub(src, '', self.render(_file, data))
                _file = fs.abspath(os.path.join(cur_dir, _file))
                _file_dest = fs.abspath(os.path.join(cur_dir_dest, new_file))

                if force is True:
                    LOG.debug('Overwriting existing file: %s ' % _file_dest)
                else:
                    assert not os.path.exists(_file_dest), \
                        'Destination file already exists: %s ' % _file_dest

                ignore_it = False
                all_patterns = self._meta.ignore + ignore
                for pattern in all_patterns:
                    if re.match(pattern, _file):
                        ignore_it = True
                        break

                if ignore_it is True:
                    self.app.log.debug(
                        'Not copying ignored file: ' +
                        '%s' % _file)
                    continue

                exclude_it = False
                all_patterns = self._meta.exclude + exclude
                for pattern in all_patterns:
                    if re.match(pattern, _file):
                        exclude_it = True
                        break

                if exclude_it is True:
                    self.app.log.debug(
                        'Not rendering excluded file as template: ' +
                        '%s' % _file)
                    shutil.copy(_file, _file_dest)
                else:
                    f = open(os.path.join(cur_dir, _file), 'r')
                    content = f.read()
                    f.close()

                    _file_content = self.render(content, data)
                    f = open(_file_dest, 'w')
                    f.write(_file_content)
                    f.close()

        return True

    def _load_template_from_file(self, template_path):
        for template_dir in self.app._meta.template_dirs:
            template_prefix = template_dir.rstrip('/')
            template_path = template_path.lstrip('/')
            full_path = fs.abspath(os.path.join(template_prefix,
                                                template_path))
            LOG.debug("attemping to load output template from file %s" %
                      full_path)
            if os.path.exists(full_path):
                content = open(full_path, 'r').read()
                LOG.debug("loaded output template from file %s" %
                          full_path)
                return (content, full_path)
            else:
                LOG.debug("output template file %s does not exist" %
                          full_path)
                continue

        return (None, None)

    def _load_template_from_module(self, template_path):
        template_module = self.app._meta.template_module
        template_path = template_path.lstrip('/')
        full_module_path = "%s.%s" % (template_module,
                                      re.sub('/', '.', template_path))

        LOG.debug("attemping to load output template '%s' from module %s" %
                  (template_path, template_module))

        # see if the module exists first
        if template_module not in sys.modules:
            try:
                __import__(template_module, globals(), locals(), [], 0)
            except ImportError as e:
                LOG.debug("unable to import template module '%s'."
                          % template_module)
                return (None, None)

        # get the template content
        try:
            content = pkgutil.get_data(template_module, template_path)
            LOG.debug("loaded output template '%s' from module %s" %
                      (template_path, template_module))
            return (content, full_module_path)
        except IOError as e:
            LOG.debug("output template '%s' does not exist in module %s" %
                      (template_path, template_module))
            return (None, None)

    def load(self, template_path):
        """
        Loads a template file first from ``self.app._meta.template_dirs`` and
        secondly from ``self.app._meta.template_module``.  The
        ``template_dirs`` have presedence.

        Args:
            template_path (str): The secondary path of the template **after**
                either ``template_module`` or ``template_dirs`` prefix (set via
                ``App.Meta``)

        Returns:
            tuple: The content of the template (``str``), the type of template
            (``str``: ``directory``, or ``module``), and the path (``str``) of
            the directory or module)

        Raises:
            cement.core.exc.FrameworkError: If the template does not exist in
                either the ``template_module`` or ``template_dirs``.
        """
        if not template_path:
            raise exc.FrameworkError("Invalid template path '%s'." %
                                     template_path)

        # first attempt to load from file
        content, path = self._load_template_from_file(template_path)
        if content is None:
            # second attempt to load from module
            content, path = self._load_template_from_module(template_path)
            template_type = 'module'
        else:
            template_type = 'directory'

        # if content is None, that means we didn't find a template file in
        # either and that is an exception
        if content is None:
            raise exc.FrameworkError("Could not locate template: %s" %
                                     template_path)

        return (content, template_type, path)