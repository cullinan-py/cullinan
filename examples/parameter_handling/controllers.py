from cullinan import controller
from cullinan.web import Body, Path, Query, get_api, post_api


@controller(url="/catalog")
class CatalogController:
    @get_api(url="/items/{item_id}")
    def get_item(
        self,
        item_id: int = Path(ge=1),
        include_meta: bool = Query(default=False),
        locale: str = Query(default="en-US"),
    ):
        payload = {
            "item_id": item_id,
            "include_meta": include_meta,
            "locale": locale,
        }
        if include_meta:
            payload["meta"] = {"source": "parameter-system", "kind": "catalog-item"}
        return payload

    @post_api(url="/search")
    def search(
        self,
        keyword: str = Body.as_required(min_length=1),
        page: int = Body(default=1, ge=1),
        limit: int = Body(default=10, ge=1, le=50),
    ):
        return {
            "keyword": keyword,
            "page": page,
            "limit": limit,
            "strategy": "controller-method-parameters",
        }
