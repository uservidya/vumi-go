from vumi import log

from go.errors import VumiGoError


class GoRoutingTableError(VumiGoError):
    """Exception class for invalid operations on routing tables."""


class GoConnectorError(GoRoutingTableError):
    """Raised when attempting to construct an invalid connector."""


class GoConnector(object):
    """Container for Go routing table connector item."""

    # Types of connectors in Go routing tables

    CONVERSATION = "CONVERSATION"
    ROUTER = "ROUTER"
    TRANSPORT_TAG = "TRANSPORT_TAG"
    OPT_OUT = "OPT_OUT"

    # Directions for router entries

    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"

    def __init__(self, ctype, names, parts):
        self.ctype = ctype
        self._names = names
        self._parts = parts
        self._attrs = dict(zip(self._names, self._parts))

    @property
    def direction(self):
        return {
            self.OPT_OUT: self.INBOUND,
            self.CONVERSATION: self.INBOUND,
            self.TRANSPORT_TAG: self.OUTBOUND,
            self.ROUTER: self._attrs.get('direction'),
        }[self.ctype]

    def __str__(self):
        return ":".join([self.ctype] + self._parts)

    def __getattr__(self, name):
        return self._attrs[name]

    def flip_direction(self):
        if self.ctype != self.ROUTER:
            raise GoConnectorError(
                "Attempt to call .flip_direction on %r which is not a router"
                " connector." % (self,))
        direction = (self.INBOUND if self.direction == self.OUTBOUND
                     else self.OUTBOUND)
        return GoConnector.for_router(
            self.router_type, self.router_key, direction)

    @classmethod
    def for_conversation(cls, conv_type, conv_key):
        return cls(cls.CONVERSATION, ["conv_type", "conv_key"],
                   [conv_type, conv_key])

    @classmethod
    def for_router(cls, router_type, router_key, direction):
        if direction not in (cls.INBOUND, cls.OUTBOUND):
            raise GoConnectorError(
                "Invalid connector direction: %s" % (direction,))
        return cls(cls.ROUTER,
                   ["router_type", "router_key", "direction"],
                   [router_type, router_key, direction])

    @classmethod
    def for_transport_tag(cls, tagpool, tagname):
        return cls(cls.TRANSPORT_TAG, ["tagpool", "tagname"],
                   [tagpool, tagname])

    @classmethod
    def for_opt_out(cls):
        return cls(cls.OPT_OUT, [], [])

    @classmethod
    def parse(cls, s):
        parts = s.split(":")
        ctype, parts = parts[0], parts[1:]
        constructors = {
            cls.CONVERSATION: cls.for_conversation,
            cls.ROUTER: cls.for_router,
            cls.TRANSPORT_TAG: cls.for_transport_tag,
            cls.OPT_OUT: cls.for_opt_out,
        }
        if ctype not in constructors:
            raise GoConnectorError("Unknown connector type %r"
                                   " found while parsing: %r" % (ctype, s))
        try:
            return constructors[ctype](*parts)
        except TypeError:
            raise GoConnectorError("Invalid connector of type %r: %r"
                                   % (ctype, s))

    @classmethod
    def for_model(cls, model_obj, direction=None):
        """Construct an appropriate connector based on a model object.
        """
        if hasattr(model_obj, 'router_type'):
            return cls.for_router(
                model_obj.router_type, model_obj.key, direction)

        if direction is not None:
            raise GoConnectorError("Only router connectors have a direction.")

        if hasattr(model_obj, 'conversation_type'):
            return cls.for_conversation(
                model_obj.conversation_type, model_obj.key)

        # Hacky, replace when we have proper channels.
        if hasattr(model_obj, 'tagpool') and hasattr(model_obj, 'tag'):
            return cls.for_transport_tag(model_obj.tagpool, model_obj.tag)

        raise GoConnectorError(
            "Unknown object type for connector: %s" % (model_obj,))


class RoutingTable(object):
    """Interface to routing table dictionaries.

    Conceptually a routing table maps (source_connector, source_endpoint) pairs
    to (destination_connector, destination_endpoint) pairs.

    Internally this is implemented as a nested mapping::

        source_connector ->
            source_endpoint_1 -> [destination_connector, destination_endpoint]
            source_endpoint_2 -> [..., ...]

    in order to make storing the mapping as JSON easier (JSON keys cannot be
    lists).
    """

    def __init__(self, routing_table=None):
        # XXX: Kill this check later.
        if isinstance(routing_table, RoutingTable):
            raise TypeError("I want a dict.")
        if routing_table is None:
            routing_table = {}
        self._routing_table = routing_table

    def __eq__(self, other):
        if not isinstance(other, RoutingTable):
            return False
        return self._routing_table == other._routing_table

    def __nonzero__(self):
        return bool(self._routing_table)

    def lookup_target(self, src_conn, src_endpoint):
        return self._routing_table.get(src_conn, {}).get(src_endpoint)

    def lookup_targets(self, src_conn):
        return self._routing_table.get(src_conn, {}).items()

    def lookup_source(self, target_conn, target_endpoint):
        for src_conn, routes in self._routing_table.iteritems():
            for src_endpoint, (dst_conn, dst_endpoint) in routes.items():
                if dst_conn == target_conn and dst_endpoint == target_endpoint:
                    return [src_conn, src_endpoint]
        return None

    def lookup_sources(self, target_conn):
        sources = []
        for src_conn, routes in self._routing_table.iteritems():
            for src_endpoint, (dest_conn, dest_endpoint) in routes.items():
                if dest_conn == target_conn:
                    sources.append((dest_endpoint, [src_conn, src_endpoint]))
        return sources

    def entries(self):
        """Iterate over entries in the routing table.

        Yield tuples of (src_conn, src_endpoint, dst_conn, dst_endpoint).
        """
        for src_conn, endpoints in self._routing_table.iteritems():
            for src_endp, (dst_conn, dst_endp) in endpoints.iteritems():
                yield (src_conn, src_endp, dst_conn, dst_endp)

    def add_entry(self, src_conn, src_endpoint, dst_conn, dst_endpoint):
        self.validate_entry(src_conn, src_endpoint, dst_conn, dst_endpoint)
        connector_dict = self._routing_table.setdefault(src_conn, {})
        if src_endpoint in connector_dict:
            log.warning(
                "Replacing routing entry for (%r, %r): was %r, now %r" % (
                    src_conn, src_endpoint, connector_dict[src_endpoint],
                    [dst_conn, dst_endpoint]))
        connector_dict[src_endpoint] = [dst_conn, dst_endpoint]

    def remove_entry(self, src_conn, src_endpoint):
        connector_dict = self._routing_table.get(src_conn)
        if connector_dict is None or src_endpoint not in connector_dict:
            log.warning(
                "Attempting to remove missing routing entry for (%r, %r)." % (
                    src_conn, src_endpoint))
            return None

        old_dest = connector_dict.pop(src_endpoint)

        if not connector_dict:
            # This is the last entry for this connector
            self._routing_table.pop(src_conn)

        return old_dest

    def remove_connector(self, conn):
        """Remove all references to the given connector.

        Useful when the connector is going away for some reason.
        """
        # remove entries with connector as source
        self._routing_table.pop(conn, None)

        # remove entires with connector as destination
        to_remove = []
        for src_conn, routes in self._routing_table.iteritems():
            for src_endpoint, (dest_conn, dest_endpoint) in routes.items():
                if dest_conn == conn:
                    del routes[src_endpoint]
            if not routes:
                # We can't modify this dict while iterating over it.
                to_remove.append(src_conn)

        for src_conn in to_remove:
            del self._routing_table[src_conn]

    def remove_conversation(self, conv):
        """Remove all entries linking to or from a given conversation.

        Useful when archiving a conversation to ensure it is no longer
        present in the routing table.
        """
        conv_conn = str(GoConnector.for_conversation(conv.conversation_type,
                                                     conv.key))
        self.remove_connector(conv_conn)

    def remove_router(self, router):
        """Remove all entries linking to or from a given router.

        Useful when archiving a router to ensure it is no longer present in the
        routing table.
        """
        self.remove_connector(str(GoConnector.for_router(
            router.router_type, router.key, GoConnector.INBOUND)))
        self.remove_connector(str(GoConnector.for_router(
            router.router_type, router.key, GoConnector.OUTBOUND)))

    def remove_transport_tag(self, tag):
        """Remove all entries linking to or from a given transport tag.

        Useful when releasing a tag to ensure it is no longer present in the
        routing table.
        """
        tag_conn = str(GoConnector.for_transport_tag(tag[0], tag[1]))
        self.remove_connector(tag_conn)

    def add_oldstyle_conversation(self, conv, tag, outbound_only=False):
        """XXX: This can be removed when old-style conversations are gone."""
        conv_conn = str(GoConnector.for_conversation(conv.conversation_type,
                                                     conv.key))
        tag_conn = str(GoConnector.for_transport_tag(tag[0], tag[1]))
        self.add_entry(conv_conn, "default", tag_conn, "default")
        if not outbound_only:
            self.add_entry(tag_conn, "default", conv_conn, "default")

    def transitive_targets(self, src_conn):
        """Return all connectors that are reachable from `src_conn`.

        Only follows routing steps from source to destination (never
        follows steps backwards from destination to source).

        Once a destination has been found, the following items are
        added to the list of things to search:

        * If the destination is a conversation, channel or opt-out
          connector no extra sources to search are added.

        * If the destination is a router, the connector on the other
          side of the router is added to the list of sources to search
          from (i.e. the inbound side if an outbound router connector
          is the target and vice versa).

        :param str src_conn: source connector to start search with.
        :rtype: set of destination connector strings.
        """
        sources = [src_conn]
        sources_seen = set(sources)
        results = set()
        while sources:
            source = sources.pop()
            destinations = self.lookup_targets(source)
            for _src_endpoint, (dst_conn, _dst_endpoint) in destinations:
                results.add(dst_conn)
                parsed_dst = GoConnector.parse(dst_conn)
                if parsed_dst.ctype != GoConnector.ROUTER:
                    continue
                extra_src = str(parsed_dst.flip_direction())
                if extra_src not in sources_seen:
                    sources.append(extra_src)
                    sources_seen.add(extra_src)
        return results

    def transitive_sources(self, dst_conn):
        """Return all connectors that lead to `dst_conn`.

        Only follows routing steps backwards from destination to
        source (never forwards from source to destination).

        Once a source has been found, the following items are
        added to the list of things to search:

        * If the sources is a conversation, channel or opt-out
          connector no extra destinations to search are added.

        * If the source is a router, the connector on the other side
          of the router is added to the list of destinations to search
          from (i.e. the inbound side if an outbound router connector
          is the source and vice versa).

        :param str dst_conn: destination connector to start search with.
        :rtype: set of source connector strings.
        """
        destinations = [dst_conn]
        destinations_seen = set(destinations)
        results = set()
        while destinations:
            destination = destinations.pop()
            sources = self.lookup_sources(destination)
            for _dst_endpoint, (src_conn, _src_endpoint) in sources:
                results.add(src_conn)
                parsed_src = GoConnector.parse(src_conn)
                if parsed_src.ctype != GoConnector.ROUTER:
                    continue
                extra_dst = str(parsed_src.flip_direction())
                if extra_dst not in destinations_seen:
                    destinations.append(extra_dst)
                    destinations_seen.add(extra_dst)
        return results

    def validate_entry(self, src_conn, src_endpoint, dst_conn, dst_endpoint):
        """Validate the provided entry.

        This method currently only validates that the source and destination
        have opposite directionality (IN->OUT or OUT->IN).
        """
        parsed_src = GoConnector.parse(src_conn)
        parsed_dst = GoConnector.parse(dst_conn)
        if parsed_src.direction == parsed_dst.direction:
            raise ValueError(
                "Invalid routing table entry: %s source (%s, %s) maps to %s"
                " destination (%s, %s)" % (
                    parsed_src.direction, src_conn, src_endpoint,
                    parsed_dst.direction, dst_conn, dst_endpoint))

    def validate_all_entries(self):
        """Validates all entries in the routing table.
        """
        for entry in self.entries():
            self.validate_entry(*entry)
