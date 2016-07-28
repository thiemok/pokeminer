/*
	Created by Devsome
	thanks to imDevinC https://github.com/ImDevinC/pkgo-discord for the functions
	edited for https://github.com/modrzew/pokeminer
*/
var Discord = require("discord.js");
var request = require("request");
var NodeGeocoder = require('node-geocoder');
var fs = require("fs");

// Loading my Configs
var config = require("./bot/config.json");
var locale = require("./locales/pokemon."+config.locale+".json");

var clientBot = new Discord.Client();

var alreadySeen = [];
var joinUrl = "https://discordapp.com/oauth2/authorize?client_id=" + config.app_id + "&scope=bot&permissions=";
var mapUrl = 'http://maps.google.com/maps?&z=10&ll={0}+{1}&q={0}+{1}';
var options = {
  provider: 'google',
  httpAdapter: 'https',
  apiKey: config.gmap_key, 
  formatter: null
};
var geocoder = NodeGeocoder(options);

clientBot.on("ready", function () {
	console.log("\n[INFO]\tTo add me visit this url:\n\t" + joinUrl + "\n\n");
	console.log("[INFO]\tReady to begin!");
	console.log("[INFO]\tYou're connected to [ " + clientBot.servers.length + " ] Servers with [" + clientBot.channels.length + "] Channels!");

	clientBot.setPlayingGame( config.games[Math.floor(Math.random() * (config.games.length))] );
});

clientBot.on('disconnected', function() {
	console.log("Disconnted ? Let me reconnect asap...");
	clientBot.loginWithToken(config.token);
});

clientBot.on("error", function (error) {
	console.log("Caught error: " + error);
});

// CMD+C at terminal
process.on("SIGINT", function () {
	console.log("\n Whoa wait, let me logout first...");
	clientBot.logout();
	process.exit(1);
});

function checkPokemon() {
	request('http://' + config.getServer + '/discord', (err, res, body) => {
		if (err) {
			console.log(err);
			return;
		}
		if (200 != res.statusCode) {
			console.log('Invalid response code: ' + res.statusCode);
			return;
		}
		parsePokemon(JSON.parse(body));
	});
}

function parsePokemon(results) {
	var config = require("./bot/config.json");
	if (!Object.keys(results) || Object.keys(results).length < 1) {
		return;
	}
	foundPokemon = [];
	for (pokemon in results) {
		if(config.pokeShow.indexOf(results[pokemon].pokemon_id) >= 0 ) {
			// found
		} else {
			continue; // not found
		}
		foundPokemon.push(results[pokemon].key);
		if (alreadySeen.indexOf(results[pokemon].key) > -1) {
			continue;
		}

		newPokemonSighted(results[pokemon]);
		alreadySeen.push(results[pokemon].key);
	}

	clearStalePokemon(foundPokemon);
}

function clearStalePokemon(pokemons) {
	var oldSeen = alreadySeen;
	for (id in oldSeen) {
		var pokemon = pokemons.indexOf(oldSeen[id]);
		if (pokemon > -1) {
			continue;
	}

	var index = alreadySeen.indexOf(oldSeen[id]);
		alreadySeen.splice(index, 1);
	}
}

function newPokemonSighted(pokemon) {
	var diff = new Date(pokemon.disappear_time * 1000) - Date.now();
	diff = Math.floor(diff / 1000);
	diff = Math.floor(diff / 60);
	min_diff = diff % 60;
	var url = mapUrl.split('{0}').join(pokemon.lat);
	url = url.split('{1}').join(pokemon.lng);

	geocoder.reverse({lat:pokemon.lat, lon:pokemon.lng}, function(err, res) {
		var streetName = res[0].formattedAddress;
		var message = '**' + pokemon.name + '** (' + pokemon.pokemon_id + ') gesichtet ! Verschwindet in **' + min_diff + '** minuten \n'+streetName+'';  
		clientBot.sendFile( config.channelID , __dirname + "/bot/img/"+ pokemon.pokemon_id +".png" , pokemon.pokemon_id +".png", message, (err, msg) => {
			if (err) {
				clientBot.sendMessage(config.channelID, "I do not have the rights to send a **file** :cry:!");
			}
		});
	});
}

clientBot.on("message", function (msg) {

	if(msg.author.id != clientBot.user.id && msg.content[0] === '!'){
		var cmdTxt = msg.content.split(" ")[0].substring(1);
		var suffix = msg.content.substring(cmdTxt.length+2);
	
		if( cmdTxt == "read" ) {
			var config = require( __dirname + '/bot/config.json' );
			clientBot.sendMessage(msg.channel, "Das sind die Eingetragenen Pokémon\n```\n" + config.pokeShow + "```", function(err, msg){
				// 
			});
		}

		if( cmdTxt == "add" ) {
			if (suffix) {
				var config = require( __dirname + '/bot/config.json' );
				
				var newItem = parseInt(suffix);
				var array = config.pokeShow;

				if (array.indexOf(newItem) == -1) {
					array.push(newItem);
					clientBot.sendMessage(msg.channel, "Pokémon **"+suffix+" - "+locale[suffix]+"** wurde gespeichert :rainbow: ", function(err, msg){
						// 
					});
				} else {
					clientBot.sendMessage(msg.channel, "Pokémon **"+suffix+" - "+locale[suffix]+"** ist schon in der Liste :warning:  ", function(err, msg){
						//
					});
				}
				config.pokeShow = config.pokeShow;
				fs.writeFileSync( __dirname + '/bot/config.json' , JSON.stringify(config));
				delete require.cache[ __dirname + '/bot/config.json' ]
			} else {
				clientBot.sendMessage(msg.channel, "Bitte gib eine ID an, zum Beispiel:  ``!add 1``  :point_up:", function(err, msg){
					// 
				});
			}
		}
		
		if( cmdTxt == "del" ) {
			if (suffix) {
				var config = require( __dirname + '/bot/config.json' );
				
				var newItem = parseInt(suffix);
				var array = config.pokeShow;

				if (array.indexOf(newItem) == -1) {
					clientBot.sendMessage(msg.channel, "Pokémon **"+suffix+" - "+locale[suffix]+"** befindet sich nicht in der Liste :warning:  ", function(err, msg){
						// 
					});
				} else {
					var i = array.indexOf(newItem);
					if(i != -1) {
						array.splice(i, 1);
					}
					clientBot.sendMessage(msg.channel, "Pokémon **"+suffix+" - "+locale[suffix]+"** wurde gelöscht :rainbow: ", function(err, msg){
						// 
					});
				}
				config.pokeShow = config.pokeShow;
				fs.writeFileSync( __dirname + '/bot/config.json' , JSON.stringify(config));
				delete require.cache[ __dirname + '/bot/config.json' ]
			} else {
				clientBot.sendMessage(msg.channel, "Bitte gib eine ID an, zum Beispiel:  ``!del 1``  :point_up:", function(err, msg){
					// 
				});
			}
		}
	
	} else if (msg.author != clientBot.user && msg.isMentioned(clientBot.user)) { // If someone @called the Bot
			clientBot.sendMessage(msg.channel ,msg.author + ", mit ``!add 1`` kannst du Pokemon hinzufügen & ``!del 1`` es wieder löschen ! :cool:");
	}

});


/* TOKEN */
clientBot.loginWithToken(config.token, (err, token) => {
	if (err) { console.log(err); setTimeout(() => { process.exit(1); }, 2000); }
	if (!token) { console.log(" WARN " + " failed to connect"); setTimeout(() => { process.exit(0); }, 2000); }
});

/* Changing game playing */
setInterval(() => {
	clientBot.setPlayingGame(config.games[Math.floor(Math.random() * (config.games.length))]);
}, (10 * 1000) * 60); //change playing game every 10 minutes

/* checking for new pokemon */
setInterval(() => {
	checkPokemon();
}, (config.CheckMinutes * 1000) * 10); //checking for Pokemon every x minutes
