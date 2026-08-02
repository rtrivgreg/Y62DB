"""Lambda entry point + router.

A single Lambda function fronts every route in the API Gateway REST API
(each method uses AWS_PROXY integration to this function). The router below
dispatches on (httpMethod, resource) — `resource` is API Gateway's templated
path, e.g. "/rules/{ruleId}/bindings/{group}/{binding}" — to the matching
resource module, and wraps every call in centralized error handling so all
failure modes produce the same standardized response envelope.

Route table (kept in sync with README.md's API contract):

    GET    /rules/{ruleId}/bindings                  -> bindings.list_by_rule.handle
    POST   /rules/{ruleId}/bindings                  -> bindings.create.handle
    GET    /rules/{ruleId}/bindings/{group}/{binding} -> bindings.get.handle
    PUT    /rules/{ruleId}/bindings/{group}/{binding} -> bindings.update.handle
    DELETE /rules/{ruleId}/bindings/{group}/{binding} -> bindings.delete.handle
    GET    /groups/{group}/bindings                  -> bindings.list_by_group.handle
    GET    /rules                                    -> rules.list_ids.handle (catalog + bindings, see §12.11)
    GET    /rules/{ruleId}/catalog                   -> rules.get_catalog.handle
    GET    /groups                                   -> groups.list_ids.handle
"""
import logging

from bindings import create, delete, get, list_by_group, list_by_rule, update
from common import response
from common.exceptions import ApiError
from groups import list_ids as groups_list_ids
from rules import get_catalog, list_ids as rules_list_ids

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ROUTES = {
    ("GET", "/rules/{ruleId}/bindings"): list_by_rule.handle,
    ("POST", "/rules/{ruleId}/bindings"): create.handle,
    ("GET", "/rules/{ruleId}/bindings/{group}/{binding}"): get.handle,
    ("PUT", "/rules/{ruleId}/bindings/{group}/{binding}"): update.handle,
    ("DELETE", "/rules/{ruleId}/bindings/{group}/{binding}"): delete.handle,
    ("GET", "/groups/{group}/bindings"): list_by_group.handle,
    ("GET", "/rules"): rules_list_ids.handle,
    ("GET", "/rules/{ruleId}/catalog"): get_catalog.handle,
    ("GET", "/groups"): groups_list_ids.handle,
}


def lambda_handler(event, context):
    request_id = getattr(context, "aws_request_id", None)
    http_method = event.get("httpMethod", "").upper()
    resource = event.get("resource", event.get("path", ""))

    # CORS preflight is handled at the API Gateway MOCK integration in
    # Terraform, but this guard keeps the Lambda safe if it's ever invoked
    # directly for OPTIONS.
    if http_method == "OPTIONS":
        return response.success(200, data=None)

    route_handler = ROUTES.get((http_method, resource))
    if route_handler is None:
        logger.warning("No route for %s %s", http_method, resource)
        return response.error(
            404,
            "route_not_found",
            f"No route matches {http_method} {resource}.",
            request_id=request_id,
        )

    try:
        return route_handler(event, context)
    except ApiError as exc:
        logger.info("Handled API error on %s %s: %s", http_method, resource, exc.message)
        return response.error(exc.status_code, exc.error_code, exc.message, exc.details, request_id)
    except Exception:  # noqa: BLE001 - last line of defense, always return the envelope
        logger.exception("Unhandled exception on %s %s", http_method, resource)
        return response.error(
            500,
            "internal_error",
            "An unexpected error occurred while processing the request.",
            request_id=request_id,
        )
