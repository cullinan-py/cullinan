from typing import TYPE_CHECKING

from cullinan.web import Path, WebResponse, controller, get_api

if TYPE_CHECKING:
    from .services import UserDirectoryService


@controller(url="/users")
class UserController:
    user_directory: UserDirectoryService  # ← constructor injection: one line is enough

    @get_api(url="")
    def list_users(self):
        users = self.user_directory.list_users()
        return {"items": users, "count": len(users)}

    @get_api(url="/{user_id}")
    def get_user(self, user_id: int = Path(ge=1)):
        user = self.user_directory.get_user(user_id)
        if user is None:
            return WebResponse.json({"message": "User not found."}, status_code=404)
        return user
