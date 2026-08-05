class UsersController < ApplicationController
  def bad1
    # ruleid: rails-mass-assignment-permit-bang
    User.create(params.require(:user).permit!)
  end

  def ok1
    # ok: rails-mass-assignment-permit-bang
    User.create(params.require(:user).permit(:name, :email))
  end
end
