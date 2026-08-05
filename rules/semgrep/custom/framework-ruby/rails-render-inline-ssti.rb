class PagesController < ApplicationController
  def bad1
    # ruleid: rails-render-inline-ssti
    render inline: "<h1>Hello #{params[:name]}</h1>"
  end

  def ok1
    # ok: rails-render-inline-ssti
    render inline: "<h1>Static content</h1>"
  end
end
