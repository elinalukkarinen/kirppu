from functools import wraps
import json
import django.forms
from django.http.response import HttpResponseBadRequest, HttpResponse, HttpResponseForbidden
from django.utils.translation import ugettext as _i

__author__ = 'jyrkila'

RFC2822TIME = "%a, %d %b %Y %H:%M:%S %z"


class AjaxError(RuntimeError):
    def __init__(self, *args, **kwargs):
        status = kwargs.pop("status", None)
        super(AjaxError, self).__init__(*args, **kwargs)
        self._status = status

    @property
    def status(self):
        return self._status


def ajax_request(fn):
    """
    Decorator for django views that are meant purely for AJAX access.
    """
    @wraps(fn)
    def inner(request, *args, **kwargs):
        if not request.is_ajax():
            return HttpResponseBadRequest("Invalid requester")

        try:
            result = fn(request, *args, **kwargs)
        except AjaxError as e:
            result = e.status or 500, e.message

        if isinstance(result, HttpResponse):
            # return HttpResponse(...)
            return result

        if isinstance(result, int):
            # return 200
            return HttpResponse(status=result)

        status_code = 200
        if isinstance(result, tuple):
            # return 200, {...}
            status_code = result[0]
            result = result[1]

        if isinstance(result, (str, unicode)):
            # return 200, "..."
            result = {"message": result}

        return HttpResponse(json.dumps(result), status=status_code, mimetype="application/json")
    return inner


def model_dict_fn(*args, **kwargs):
    """
    Return a function that will create dictionary by reading values from class instance.

        >>> class C(object):
        ...     def __init__(self):
        ...         self.a = 3
        ...     as_dict = model_dict_fn("a")
        ...     as_renamed = model_dict_fn(renamed="a")
        ...     as_called = model_dict_fn(multi=lambda self: self.a * 2)
        >>> C().as_dict(), C().as_renamed(), C().as_called()
        ({'a': 3}, {'renamed': 3}, {'multi': 6})

    :param args: List of fields.
    :param kwargs: Fields to be renamed or overridden with another function call.
    :return: Function.
    """
    fields = {}
    for plain_key in args:
        fields[plain_key] = plain_key
    fields.update(kwargs)

    def model_dict(self):
        """
        Get model fields as dictionary (for JSON/AJAX usage). Fields returned:
        {0}
        """
        ret = {}
        for key, value in fields.items():
            if callable(value):
                ret[key] = value(self)
            elif value is None:
                if value in ret:
                    del ret[value]
            else:
                ret[key] = getattr(self, value)
        return ret
    model_dict.__doc__ = model_dict.__doc__.format(", ".join(fields.keys()))
    return model_dict


def format_datetime(dt):
    """
    Format given datetime in RFC2822 format, that is used in web/javascript.

    :param dt: Datetime to format.
    :type dt: datetime.datetime
    :return: Formatted string.
    :rtype: str
    """

    return dt.strftime(RFC2822TIME)


class StaticTextWidget(django.forms.widgets.Widget):
    """
    Static text-field widget. Text should be set with set_text().
    Otherwise `initial`-text is used, or empty string as fallback.
    The resulting text is rendered instead of any widget.
    """
    def __init__(self, **kwargs):
        super(StaticTextWidget, self).__init__(**kwargs)
        self._static_text = None

    def set_text(self, text):
        self._static_text = text

    def has_text(self):
        return self._static_text is not None

    def render(self, name, value, attrs=None):
        return self._static_text or value or u""


class StaticText(django.forms.CharField):
    """
    Static text-field using StaticTextWidget. Only required parameter is `text`.
    Other parameters as per `CharField`.
    """
    def __init__(self, text, **kwargs):
        kwargs.setdefault("widget", StaticTextWidget)
        kwargs["required"] = False
        super(StaticText, self).__init__(**kwargs)

        if isinstance(self.widget, StaticTextWidget) and not self.widget.has_text():
            self.widget.set_text(text)


def require_setting(setting, value):
    """
    Decorator that requires a setting in settings to be a certain value before continuing to the view.

    :param setting: Setting key to find from settings.
    :type setting: str
    :param value: Accepted value, or one-argument callable returning True if accepted and False otherwise.
    :type value: T | callable
    :return: View decorator that will test the specified setting.
    """
    def decorator(fn):
        from django.conf import settings
        callback = callable(value)

        @wraps(fn)
        def inner(request, *args, **kwargs):
            current_value = getattr(settings, setting, None)
            if not ((not callback and current_value == value) or (callback and value(current_value))):
                return HttpResponseForbidden(_i(u"Forbidden"))
            return fn(request, *args, **kwargs)
        return inner
    return decorator
