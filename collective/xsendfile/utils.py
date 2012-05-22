"""

    XSendFile download support for BLOBs

"""
from datetime import datetime
import logging
import re

from Acquisition import aq_base
from zope import component
from zope.component import ComponentLookupError
from webdav.common import rfc1123_date
from zope.component import getUtility

from Products.Archetypes.utils import contentDispositionHeader
from plone.app.blob.config import blobScalesAttr
from plone.app.blob.utils import openBlob
from plone.app.imaging.traverse import ImageScale
from plone.i18n.normalizer.interfaces import IUserPreferredFileNameNormalizer
from plone.registry.interfaces import IRegistry

from collective.xsendfile.interfaces import IxsendfileSettings

logger = logging.getLogger('collective.xsendfile')


def index_html(self, instance=None, REQUEST=None, RESPONSE=None,
    disposition='inline'):
    """ Inject X-Sendfile and X-Accel-Redirect headers into response. """

    try:
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IxsendfileSettings)
    except ComponentLookupError:
        # This happens when collective.xsendfile egg is in place
        # but add-on installer has not been run yet
        settings = None
        logger.warn("Could not load collective.xsendfile settings")

    if REQUEST is None:
        REQUEST = instance.REQUEST
    if RESPONSE is None:
        RESPONSE = REQUEST.RESPONSE
    filename = self.getFilename(instance)
    if filename is not None:
        filename = IUserPreferredFileNameNormalizer(REQUEST).normalize(
            unicode(filename, instance.getCharset()))
        header_value = contentDispositionHeader(
            disposition=disposition,
            filename=filename)
        RESPONSE.setHeader("Content-disposition", header_value)

    blob = self.getUnwrapped(instance, raw=True)    # TODO: why 'raw'?
    zodb_blob = blob.getBlob()
    blob_file = zodb_blob.open()
    file_path = blob_file.name
    blob_file.close()

    RESPONSE.setHeader('Last-Modified', rfc1123_date(instance._p_mtime))
    RESPONSE.setHeader("Content-Length", blob.get_size())
    RESPONSE.setHeader('Content-Type', self.getContentType(instance))

    if settings is not None:
        responseheader = settings.xsendfile_responseheader
        pathregex_search = settings.xsendfile_pathregex_search
        pathregex_substitute = settings.xsendfile_pathregex_substitute
        enable_fallback = settings.xsendfile_enable_fallback

        if responseheader and pathregex_substitute:
            file_path = re.sub(pathregex_search, pathregex_substitute,
                               file_path)

        fallback = False
        if not responseheader:
            fallback = True
            logger.warn("No front end web server type selected")
        if enable_fallback:
            if (not REQUEST.get('HTTP_X_FORWARDED_FOR')):
                fallback = True

    else:
        # Not yet installed through add-on installer
        fallback = True

    if fallback:
        logger.warn("Falling back to sending object %s.%s via Zope" % \
                    (repr(instance), repr(self)))
        return zodb_blob.open().read()
    else:
        logger.debug("Sending object %s.%s with xsendfile header %s, path: "
                     "%s" % (repr(instance), repr(self),
                             repr(responseheader), repr(file_path)))
        RESPONSE.setHeader(responseheader, file_path)
        return "collective.xsendfile - proxy missing?"


def ImageScale_index_html(self):
    """ Inject X-Sendfile and X-Accel-Redirect headers into response. """

    try:
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IxsendfileSettings)
    except ComponentLookupError:
        # This happens when collective.xsendfile egg is in place
        # but add-on installer has not been run yet
        settings = None
        logger.warn("Could not load collective.xsendfile settings")

    instance = self.aq_parent
    disposition = 'inline'
    REQUEST = None
    RESPONSE = None
    if REQUEST is None:
        REQUEST = self.REQUEST
    if RESPONSE is None:
        RESPONSE = REQUEST.RESPONSE
    filename = self.filename
    if filename is not None:
        filename = IUserPreferredFileNameNormalizer(REQUEST).normalize(
            unicode(filename, self.getCharset()))
        header_value = contentDispositionHeader(disposition=disposition,
                                                filename=filename)
        RESPONSE.setHeader("Content-disposition", header_value)

    file_path = self.blobfile

    RESPONSE.setHeader('Last-Modified', rfc1123_date(instance._p_mtime))
    RESPONSE.setHeader("Content-Length", self.size)
    RESPONSE.setHeader('Content-Type', self.content_type)

    if settings is not None:
        responseheader = settings.xsendfile_responseheader
        pathregex_search = settings.xsendfile_pathregex_search
        pathregex_substitute = settings.xsendfile_pathregex_substitute
        enable_fallback = settings.xsendfile_enable_fallback

        if responseheader and pathregex_substitute:
            file_path = re.sub(pathregex_search, pathregex_substitute,
                               file_path)

        fallback = False
        if not responseheader:
            fallback = True
            logger.warn("No front end web server type selected")
        if enable_fallback:
            if (not REQUEST.get('HTTP_X_FORWARDED_FOR')):
                fallback = True

    else:
        # Not yet installed through add-on installer
        fallback = True

    if fallback:
        logger.warn("Falling back to sending object %s.%s via Zope" % \
                    (repr(instance), repr(self)))
        return openBlob(self.blob).read()
    else:
        logger.debug("Sending object %s.%s with xsendfile header %s, path: "
                     "%s" % (repr(instance), repr(self),
                             repr(responseheader), repr(file_path)))
        RESPONSE.setHeader(responseheader, file_path)
        return "collective.xsendfile - proxy missing?"


def retrieveScale(self, instance, scale):
    """ retrieve a scaled version of the image """
    field = self.context
    if scale is None:
        blob = field.getUnwrapped(instance)
        data = dict(id=field.getName(), blob=blob.getBlob(),
            content_type=blob.getContentType(),
            filename=blob.getFilename())
    else:
        fields = getattr(aq_base(instance), blobScalesAttr, {})
        scales = fields.get(field.getName(), {})
        data = scales.get(scale)
    if data is not None:
        blob = openBlob(data['blob'])
        # `updata_data` & friends (from `OFS`) should support file
        # objects, so we could use something like:
        #   ImageScale(..., data=blob.getIterator(), ...)
        # but it uses `len(data)`, so we'll stick with a string for now
        image = ImageScale(data['id'], data=blob.read(), blobfile=blob.name,
            blob=data['blob'], content_type=data['content_type'],
            filename=data['filename'])
        blob.close()
        return image.__of__(instance)
    return None


def make(self, info):
    """ instantiate an object implementing `IImageScale` """
    mimetype = info['mimetype']
    info['content_type'] = mimetype
    info['filename'] = self.context.getFilename()
    blob = openBlob(info['data'])
    info['blobfile'] = blob.name
    blob.close()
    info['blob'] = info['data']
    scale = ImageScale(info['uid'], **info)
    scale.size = len(scale.data)
    url = self.context.absolute_url()
    extension = mimetype.split('/')[-1]
    scale.url = '%s/@@images/%s.%s' % (url, info['uid'], extension)
    return scale
