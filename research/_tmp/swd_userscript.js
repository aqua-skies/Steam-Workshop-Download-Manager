// ==UserScript==
// @name           SteamWorkshop.Download Button
// @namespace      http://vova1234.com/blog/web/69.html
// @description    Adds a button to the Steam Workshop pages that lets you head straight to the specific addon page at steamworkshop.download
// @include        *steamcommunity.com/sharedfiles/filedetails/?id=*
// @version        0.0.1
// @downloadURL    http://st.abcvg.info/swd/steamwd.user.js
// ==/UserScript==

var patt=new RegExp("[0-9]{2,15}");
var id = patt.exec(document.URL);

var realButton = document.getElementById("SubscribeItemBtn");

// shorten the text in the box because it will be in the way
realButton.parentNode.getElementsByTagName("h1")[0].innerHTML = "Download/Subscribe to the right";

var myButtonPosition = realButton.offsetWidth + 20;

var button = document.createElement('a');
button.setAttribute('class', 'btn_green_white_innerfade btn_border_2px btn_medium');
button.setAttribute('href', 'http://steamworkshop.download/download/view/' + id);
button.setAttribute('style', 'right: ' + myButtonPosition + 'px;');

button.innerHTML = '<div class="subscribeIcon"></div>' +
    '<span class="subscribeText">' +
    '<div class="subscribeOption subscribe selected" id="SubscribeItemOptionAdd">Download</div>' +
    '</span>';

// append the element after the real subscribe button
if (realButton.nextSibling)
{
    realButton.parentNode.insertBefore(button, realButton.nextSibling);
}
else
{
    realButton.parentNode.appendChild(button);
}
