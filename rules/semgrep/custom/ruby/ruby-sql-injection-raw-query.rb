class UsersController < ApplicationController
  def bad1
    # ruleid: ruby-sql-injection-raw-query
    User.where("name = '#{params[:name]}'")
  end

  def bad2
    # ruleid: ruby-sql-injection-raw-query
    User.find_by_sql("SELECT * FROM users WHERE id = #{params[:id]}")
  end

  def bad3
    # ruleid: ruby-sql-injection-raw-query
    ActiveRecord::Base.connection.execute("DELETE FROM sessions WHERE token = '#{params[:token]}'")
  end

  def ok1
    # ok: ruby-sql-injection-raw-query
    User.where("name = ?", params[:name])
  end

  def ok2
    # ok: ruby-sql-injection-raw-query
    User.where(name: params[:name])
  end
end
