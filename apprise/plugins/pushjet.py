# BSD 2-Clause License
#
# Apprise - Push Notification Library.
# Copyright (c) 2025, Chris Caron <lead2gold@gmail.com>
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from json import dumps

import requests

from ..common import NotifyType
from ..locale import gettext_lazy as _
from ..url import PrivacyMode
from ..utils.parse import validate_regex
from .base import NotifyBase


class NotifyPushjet(NotifyBase):
    """A wrapper for Pushjet Notifications."""

    # The default descriptive name associated with the Notification
    service_name = "Pushjet"

    # The default protocol
    protocol = "pjet"

    # The default secure protocol
    secure_protocol = "pjets"

    # A URL that takes you to the setup/help of the specific protocol
    setup_url = "https://github.com/caronc/apprise/wiki/Notify_pushjet"

    # Disable throttle rate for Pushjet requests since they are normally
    # local anyway (the remote/online service is no more)
    request_rate_per_sec = 0

    # Define object templates
    templates = (
        "{schema}://{host}:{port}/{secret_key}",
        "{schema}://{host}/{secret_key}",
        "{schema}://{user}:{password}@{host}:{port}/{secret_key}",
        "{schema}://{user}:{password}@{host}/{secret_key}",
    )

    # Define our tokens
    template_tokens = dict(
        NotifyBase.template_tokens,
        **{
            "host": {
                "name": _("Hostname"),
                "type": "string",
                "required": True,
            },
            "port": {
                "name": _("Port"),
                "type": "int",
                "min": 1,
                "max": 65535,
            },
            "secret_key": {
                "name": _("Secret Key"),
                "type": "string",
                "required": True,
                "private": True,
            },
            "user": {
                "name": _("Username"),
                "type": "string",
            },
            "password": {
                "name": _("Password"),
                "type": "string",
                "private": True,
            },
        },
    )

    template_args = dict(
        NotifyBase.template_args,
        **{
            "secret": {
                "alias_of": "secret_key",
            },
        },
    )

    def __init__(self, secret_key, **kwargs):
        """Initialize Pushjet Object."""
        super().__init__(**kwargs)

        # Secret Key (associated with project)
        self.secret_key = validate_regex(secret_key)
        if not self.secret_key:
            msg = (
                f"An invalid Pushjet Secret Key ({secret_key}) was specified."
            )
            self.logger.warning(msg)
            raise TypeError(msg)

        return

    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
        return (
            self.secure_protocol if self.secure else self.protocol,
            self.user,
            self.password,
            self.host,
            self.port,
            self.secret_key,
        )

    def url(self, privacy=False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""

        # Our URL parameters
        params = self.url_parameters(privacy=privacy, *args, **kwargs)

        default_port = 443 if self.secure else 80

        # Determine Authentication
        auth = ""
        if self.user and self.password:
            auth = "{user}:{password}@".format(
                user=NotifyPushjet.quote(self.user, safe=""),
                password=self.pprint(
                    self.password, privacy, mode=PrivacyMode.Secret, safe=""
                ),
            )

        return "{schema}://{auth}{hostname}{port}/{secret}/?{params}".format(
            schema=self.secure_protocol if self.secure else self.protocol,
            auth=auth,
            # never encode hostname since we're expecting it to be a valid one
            hostname=self.host,
            port=(
                ""
                if self.port is None or self.port == default_port
                else f":{self.port}"
            ),
            secret=self.pprint(
                self.secret_key, privacy, mode=PrivacyMode.Secret, safe=""
            ),
            params=NotifyPushjet.urlencode(params),
        )

    def send(self, body, title="", notify_type=NotifyType.INFO, **kwargs):
        """Perform Pushjet Notification."""

        params = {
            "secret": self.secret_key,
        }

        # prepare Pushjet Object
        payload = {
            "message": body,
            "title": title,
            "link": None,
            "level": None,
        }

        headers = {
            "User-Agent": self.app_id,
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        }

        auth = None
        if self.user:
            auth = (self.user, self.password)

        notify_url = "{schema}://{host}{port}/message/".format(
            schema="https" if self.secure else "http",
            host=self.host,
            port=f":{self.port}" if self.port else "",
        )

        self.logger.debug(
            "Pushjet POST URL:"
            f" {notify_url} (cert_verify={self.verify_certificate!r})"
        )
        self.logger.debug(f"Pushjet Payload: {payload!s}")

        # Always call throttle before any remote server i/o is made
        self.throttle()

        try:
            r = requests.post(
                notify_url,
                params=params,
                data=dumps(payload),
                headers=headers,
                auth=auth,
                verify=self.verify_certificate,
                timeout=self.request_timeout,
            )
            if r.status_code != requests.codes.ok:
                # We had a problem
                status_str = NotifyPushjet.http_response_code_lookup(
                    r.status_code
                )

                self.logger.warning(
                    "Failed to send Pushjet notification: "
                    "{}{}error={}.".format(
                        status_str, ", " if status_str else "", r.status_code
                    )
                )

                self.logger.debug(f"Response Details:\r\n{r.content}")

                # Return; we're done
                return False

            else:
                self.logger.info("Sent Pushjet notification.")

        except requests.RequestException as e:
            self.logger.warning(
                "A Connection error occurred sending Pushjet "
                f"notification to {self.host}."
            )
            self.logger.debug(f"Socket Exception: {e!s}")

            # Return; we're done
            return False

        return True

    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object.

        Syntax:
           pjet://hostname/secret_key
           pjet://hostname:port/secret_key
           pjet://user:pass@hostname/secret_key
           pjet://user:pass@hostname:port/secret_key
           pjets://hostname/secret_key
           pjets://hostname:port/secret_key
           pjets://user:pass@hostname/secret_key
           pjets://user:pass@hostname:port/secret_key
        """
        results = NotifyBase.parse_url(url)
        if not results:
            # We're done early as we couldn't load the results
            return results

        try:
            # Retrieve our secret_key from the first entry in the url path
            results["secret_key"] = NotifyPushjet.split_path(
                results["fullpath"]
            )[0]

        except IndexError:
            # no secret key specified
            results["secret_key"] = None

        # Allow over-riding the secret by specifying it as an argument
        # this allows people who have http-auth infront to login
        # through it in addition to supporting the secret key
        if "secret" in results["qsd"] and len(results["qsd"]["secret"]):
            results["secret_key"] = NotifyPushjet.unquote(
                results["qsd"]["secret"]
            )

        return results
