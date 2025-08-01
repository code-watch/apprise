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

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import common
from .asset import AppriseAsset
from .config.base import ConfigBase
from .logger import logger
from .manager_config import ConfigurationManager
from .url import URLBase
from .utils.logic import is_exclusive_match
from .utils.parse import GET_SCHEMA_RE, parse_list

if TYPE_CHECKING:
    from .plugins.base import NotifyBase

# Grant access to our Configuration Manager Singleton
C_MGR = ConfigurationManager()


class AppriseConfig:
    """Our Apprise Configuration File Manager.

    - Supports a list of URLs defined one after another (text format)
    - Supports a destinct YAML configuration format
    """

    def __init__(
        self,
        paths: str | list[str] | None = None,
        asset: AppriseAsset | None = None,
        cache: bool | int = True,
        recursion: int = 0,
        insecure_includes: bool = False,
        **kwargs: Any,
    ) -> None:
        """Loads all of the paths specified (if any).

        The path can either be a single string identifying one explicit
        location, otherwise you can pass in a series of locations to scan
        via a list.

        If no path is specified then a default list is used.

        By default we cache our responses so that subsiquent calls does not
        cause the content to be retrieved again. Setting this to False does
        mean more then one call can be made to retrieve the (same) data.  This
        method can be somewhat inefficient if disabled and you're set up to
        make remote calls.  Only disable caching if you understand the
        consequences.

        You can alternatively set the cache value to an int identifying the
        number of seconds the previously retrieved can exist for before it
        should be considered expired.

        It's also worth nothing that the cache value is only set to elements
        that are not already of subclass ConfigBase()

        recursion defines how deep we recursively handle entries that use the
        `import` keyword. This keyword requires us to fetch more configuration
        from another source and add it to our existing compilation. If the
        file we remotely retrieve also has an `import` reference, we will only
        advance through it if recursion is set to 2 deep.  If set to zero
        it is off.  There is no limit to how high you set this value. It would
        be recommended to keep it low if you do intend to use it.

        insecure includes by default are disabled. When set to True, all
        Apprise Config files marked to be in STRICT mode are treated as being
        in ALWAYS mode.

        Take a file:// based configuration for example, only a file:// based
        configuration can import another file:// based one. because it is set
        to STRICT mode. If an http:// based configuration file attempted to
        import a file:// one it woul fail. However this import would be
        possible if insecure_includes is set to True.

        There are cases where a self hosting apprise developer may wish to load
        configuration from memory (in a string format) that contains import
        entries (even file:// based ones).  In these circumstances if you want
        these includes to be honored, this value must be set to True.
        """

        # Initialize a server list of URLs
        self.configs = []

        # Prepare our Asset Object
        self.asset = (
            asset if isinstance(asset, AppriseAsset) else AppriseAsset()
        )

        # Set our cache flag
        self.cache = cache

        # Initialize our recursion value
        self.recursion = recursion

        # Initialize our insecure_includes flag
        self.insecure_includes = insecure_includes

        if paths is not None:
            # Store our path(s)
            self.add(paths)

        return

    def add(
        self,
        configs: str | ConfigBase | list[str | ConfigBase],
        asset: AppriseAsset | None = None,
        tag: str | list[str] | None = None,
        cache: bool | int = True,
        recursion: int | None = None,
        insecure_includes: bool | None = None,
    ) -> bool:
        """Adds one or more config URLs into our list.

        You can override the global asset if you wish by including it with the
        config(s) that you add.

        By default we cache our responses so that subsiquent calls does not
        cause the content to be retrieved again. Setting this to False does
        mean more then one call can be made to retrieve the (same) data.  This
        method can be somewhat inefficient if disabled and you're set up to
        make remote calls.  Only disable caching if you understand the
        consequences.

        You can alternatively set the cache value to an int identifying the
        number of seconds the previously retrieved can exist for before it
        should be considered expired.

        It's also worth nothing that the cache value is only set to elements
        that are not already of subclass ConfigBase()

        Optionally override the default recursion value.

        Optionally override the insecure_includes flag. if insecure_includes is
        set to True then all plugins that are set to a STRICT mode will be a
        treated as ALWAYS.
        """

        # Initialize our return status
        return_status = True

        # Initialize our default cache value
        cache = cache if cache is not None else self.cache

        # Initialize our default recursion value
        recursion = recursion if recursion is not None else self.recursion

        # Initialize our default insecure_includes value
        insecure_includes = (
            insecure_includes
            if insecure_includes is not None
            else self.insecure_includes
        )

        if asset is None:
            # prepare default asset
            asset = self.asset

        if isinstance(configs, ConfigBase):
            # Go ahead and just add our configuration into our list
            self.configs.append(configs)
            return True

        elif isinstance(configs, str):
            # Save our path
            configs = (configs,)

        elif not isinstance(configs, (tuple, set, list)):
            logger.error(
                f"An invalid configuration path (type={type(configs)}) was "
                "specified."
            )
            return False

        # Iterate over our configuration
        for _config in configs:

            if isinstance(_config, ConfigBase):
                # Go ahead and just add our configuration into our list
                self.configs.append(_config)
                continue

            elif not isinstance(_config, str):
                logger.warning(
                    f"An invalid configuration (type={type(_config)}) was"
                    " specified."
                )
                return_status = False
                continue

            logger.debug(f"Loading configuration: {_config}")

            # Instantiate ourselves an object, this function throws or
            # returns None if it fails
            instance = AppriseConfig.instantiate(
                _config,
                asset=asset,
                tag=tag,
                cache=cache,
                recursion=recursion,
                insecure_includes=insecure_includes,
            )
            if not isinstance(instance, ConfigBase):
                return_status = False
                continue

            # Add our initialized plugin to our server listings
            self.configs.append(instance)

        # Return our status
        return return_status

    def add_config(
        self,
        content: str,
        asset: AppriseAsset | None = None,
        tag: str | list[str] | None = None,
        format: str | None = None,
        recursion: int | None = None,
        insecure_includes: bool | None = None,
    ) -> bool:
        """Adds one configuration file in it's raw format. Content gets loaded
        as a memory based object and only exists for the life of this
        AppriseConfig object it was loaded into.

        If you know the format ('yaml' or 'text') you can specify it for
        slightly less overhead during this call.  Otherwise the configuration
        is auto-detected.

        Optionally override the default recursion value.

        Optionally override the insecure_includes flag. if insecure_includes is
        set to True then all plugins that are set to a STRICT mode will be a
        treated as ALWAYS.
        """

        # Initialize our default recursion value
        recursion = recursion if recursion is not None else self.recursion

        # Initialize our default insecure_includes value
        insecure_includes = (
            insecure_includes
            if insecure_includes is not None
            else self.insecure_includes
        )

        if asset is None:
            # prepare default asset
            asset = self.asset

        if not isinstance(content, str):
            logger.warning(
                f"An invalid configuration (type={type(content)}) was"
                " specified."
            )
            return False

        logger.debug(f"Loading raw configuration: {content}")

        # Create ourselves a ConfigMemory Object to store our configuration
        instance = C_MGR["memory"](
            content=content,
            format=format,
            asset=asset,
            tag=tag,
            recursion=recursion,
            insecure_includes=insecure_includes,
        )

        if not (instance.config_format and \
                instance.config_format.value in common.CONFIG_FORMATS):
            logger.warning(
                "The format of the configuration could not be deteced."
            )
            return False

        # Add our initialized plugin to our server listings
        self.configs.append(instance)

        # Return our status
        return True

    def servers(
        self,
        tag: str | list[str] = common.MATCH_ALL_TAG,
        match_always: bool = True,
        *args: Any,
        **kwargs: Any,
    ) -> list[NotifyBase]:
        """Returns all of our servers dynamically build based on parsed
        configuration.

        If a tag is specified, it applies to the configuration sources
        themselves and not the notification services inside them.

        This is for filtering the configuration files polled for results.

        If the anytag is set, then any notification that is found set with that
        tag are included in the response.
        """

        # A match_always flag allows us to pick up on our 'any' keyword
        # and notify these services under all circumstances
        match_always = common.MATCH_ALWAYS_TAG if match_always else None

        # Build our tag setup
        #   - top level entries are treated as an 'or'
        #   - second level (or more) entries are treated as 'and'
        #
        #   examples:
        #     tag="tagA, tagB"                = tagA or tagB
        #     tag=['tagA', 'tagB']            = tagA or tagB
        #     tag=[('tagA', 'tagC'), 'tagB']  = (tagA and tagC) or tagB
        #     tag=[('tagB', 'tagC')]          = tagB and tagC

        response = []

        for entry in self.configs:

            # Apply our tag matching based on our defined logic
            if is_exclusive_match(
                logic=tag,
                data=entry.tags,
                match_all=common.MATCH_ALL_TAG,
                match_always=match_always,
            ):
                # Build ourselves a list of services dynamically and return the
                # as a list
                response.extend(entry.servers())

        return response

    @staticmethod
    def instantiate(
        url: str,
        asset: AppriseAsset | None = None,
        tag: str | list[str] | None = None,
        cache: bool | int | None = None,
        recursion: int = 0,
        insecure_includes: bool = False,
        suppress_exceptions: bool = True,
    ) -> ConfigBase | None:
        """Returns the instance of a instantiated configuration plugin based on
        the provided Config URL.

        If the url fails to be parsed, then None is returned.
        """
        # Attempt to acquire the schema at the very least to allow our
        # configuration based urls.
        schema = GET_SCHEMA_RE.match(url)
        if schema is None:
            # Plan B is to assume we're dealing with a file
            schema = "file"
            url = f"{schema}://{URLBase.quote(url)}"

        else:
            # Ensure our schema is always in lower case
            schema = schema.group("schema").lower()

            # Some basic validation
            if schema not in C_MGR:
                logger.warning(f"Unsupported schema {schema}.")
                return None

        # Parse our url details of the server object as dictionary containing
        # all of the information parsed from our URL
        results = C_MGR[schema].parse_url(url)

        if not results:
            # Failed to parse the server URL
            logger.warning(f"Unparseable URL {url}.")
            return None

        # Build a list of tags to associate with the newly added notifications
        results["tag"] = set(parse_list(tag))

        # Prepare our Asset Object
        results["asset"] = (
            asset if isinstance(asset, AppriseAsset) else AppriseAsset()
        )

        if cache is not None:
            # Force an over-ride of the cache value to what we have specified
            results["cache"] = cache

        # Recursion can never be parsed from the URL
        results["recursion"] = recursion

        # Insecure includes flag can never be parsed from the URL
        results["insecure_includes"] = insecure_includes

        if suppress_exceptions:
            try:
                # Attempt to create an instance of our plugin using the parsed
                # URL information
                cfg_plugin = C_MGR[results["schema"]](**results)

            except Exception:
                # the arguments are invalid or can not be used.
                logger.warning(f"Could not load URL: {url}")
                return None

        else:
            # Attempt to create an instance of our plugin using the parsed
            # URL information but don't wrap it in a try catch
            cfg_plugin = C_MGR[results["schema"]](**results)

        return cfg_plugin

    def clear(self) -> None:
        """Empties our configuration list."""
        self.configs[:] = []

    def server_pop(self, index: int) -> NotifyBase:
        """Removes an indexed Apprise Notification from the servers."""

        # Tracking variables
        prev_offset = -1
        offset = prev_offset

        for entry in self.configs:
            servers = entry.servers(cache=True)
            if len(servers) > 0:
                # Acquire a new maximum offset to work with
                offset = prev_offset + len(servers)

                if offset >= index:
                    # we can pop an notification from our config stack
                    return entry.pop(
                        index
                        if prev_offset == -1
                        else (index - prev_offset - 1)
                    )

                # Update our old offset
                prev_offset = offset

        # If we reach here, then we indexed out of range
        raise IndexError("list index out of range")

    def pop(self, index: int = -1) -> ConfigBase:
        """Removes an indexed Apprise Configuration from the stack and returns
        it.

        By default, the last element is removed from the list
        """
        # Remove our entry
        return self.configs.pop(index)

    def __getitem__(self, index: int) -> ConfigBase:
        """Returns the indexed config entry of a loaded apprise
        configuration."""
        return self.configs[index]

    def __bool__(self) -> bool:
        """Allows the Apprise object to be wrapped in an 'if statement'.

        True is returned if at least one service has been loaded.
        """
        return bool(self.configs)

    def __iter__(self):  # type: () -> Iterator[ConfigBase]
        """Returns an iterator to our config list."""
        return iter(self.configs)

    def __len__(self) -> int:
        """Returns the number of config entries loaded."""
        return len(self.configs)
