DMARCATION
==========

This is a milter that provides header `From` rewriting for instances where an email needs to be modified and re-sent but where the [DMARC rules](https://datatracker.ietf.org/doc/html/rfc7489) for the sending address would prevent this. Examples of emails requiring modification are messages transiting mailing lists. Any emails where the From indicates a domain/subdomain with a `reject` or `quarantine` policy would be marked as non-conformant. In order to avoid this problem the `From` address would need to be replaced by a domain/subdomain which did not have this policy. The milter achieves this by replacing the original `From` address with an alternative which can be reversed later.

In practice this is achieved by encoding the `From` address as the local part of a domain/subdomain where the relevant policy record is `none`. The original entries are added as using the `X-Original-From` header, and this is then used to reinstate the original `From` address as required.

Whilst it is expected that the milter would only be introduced into the processing where it is appropriate, it is likely that not all emails would need to be processed. To this end the processing can be applied only when named headers are either present in the message, or contain specific values.

The milter can also be configured to not perform either the forward or reverse rewriting to provide more flexibility in deployment.

The milter is configured using a file in the [CFG](https://docs.red-dove.com/cfg/intro.html) format. This reflects the fact that this milter processing was originally embedded in [postconfirm](https://github.com/ietf-tools/postconfirm) and that was the format this used. In order to ease the migration keys that were previously under the `dmarc` section will be loaded from there if they are not found at the top level.

Configuration
-------------

| Key                      | Type                            | Description                                                                                                                                                                                  |
|--------------------------|---------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| log                      | object                          | Settings relating to logging                                                                                                                                                                 |
| log.level                | string/integer                  | Log level to apply, eg `DEBUG`.                                                                                                                                                              |
| domain                   | string                          | The domain part to use when rewriting a `From` address.                                                                                                                                      |
| rewrite                  | object                          | Settings relating to the address rewriting.                                                                                                                                                  |
| rewrite.quote_char       | string                          | The character used to replace `%` when encoding hex values. Defaults to `=`.                                                                                                                 |
| rewrite.require          | object                          | Headers use to enable rewriting. If this is not present or contains no entries rewriting always occurs. If any entry matches the rewriting will occur.                                       |
| rewrite.require.*header* | true, string or list of strings | If `true` then the rewriting occurs if the named header is present. If it is a string then the header must match the string value. For a list of strings then one of the entries must match. |
| rewrite.forward          | boolean                         | Flag indicating whether rewriting should occur. Defaults to `true`.                                                                                                                          |
| rewrite.reverse          | boolean                         | Flag indicating whether the rewriting should be reversed. Defaults to `true`.                                                                                                                |
| milter_port              | integer                         | The port for the milter to listen on. Defaults to `1999`.                                                                                                                                    |
| dmarc                    | object                          | Legacy container for all of the top-level keys.                                                                                                                                              |


### Example

```
dmarc: {
    domain: "dmarc.example.com"
    rewrite: {
        require: {
            x-mailman-version: true
        }
    }
}

milter_port: 2001
```

This would listen on port 2001 and rewrite emails  in the forward and reverse directions to the `dmarc.example.com` domain if the `x-mailman-version` header is present.