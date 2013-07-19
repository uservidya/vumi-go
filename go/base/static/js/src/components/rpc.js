// go.components.rpc
// =================
// Components for rpc-ifying Backbone.

(function(exports) {
  var rpcData = function(method, model) {
    var spec = _(model).result('methods')[method];

    return JSON.stringify({
      id: uuid.v4(),
      jsonrpc: '2.0',
      method: spec.method,
      params: spec.params.map(function(p) {
        return p === 'self'
          ? model
          : model.get(p);
      })
    });
  };

  var ajaxOptions = function(method, model, options) {
    return {
      contentType: 'application/json; charset=utf-8',
      type: 'POST',
      dataType: 'json',
      data: rpcData(method, model)
    };
  };

  var sync = function(method, model, options) {
    options = _({}).extend(
      ajaxOptions(method, model, options),
      options || {});

    var success = options.success;
    if (success) { options.success = function(resp) { success(resp.result); }; }

    return Backbone.sync(method, model, options);
  };

  _.extend(exports, {
    sync: sync
  });
})(go.components.rpc = {});