/* EndUser Form related JS */

var off_radio;
var on_all_radio;
var on_list_radio;
var username_list;
var runNow;
var cleanup;

function setupForm()
{
    // setup pop up dialogs
    setupPopDialogs();


    if("{{ open_error_dialog }}"){
        $("#error_dialog").attr("style", "display:block;");
        $("#error_dialog").dialog('open');
    }

    // click listeners
    $("#error_dialog_test").live('click', function(event) {
        $("#error_dialog").dialog('open');
    });



}

function setupPopDialogs()
{
    // enduser dialogs
    $("#error_dialog").dialog(
    {
        autoOpen: false,
        width: 500,
        resizable: false,
        modal: true,
        closeOnEscape: false,
        draggable: false,
        open: function(event, ui){},//resetCleanupForm();},
        buttons: [
            {
                id:"errorStartButton",
                text:"Continue",
                click:function(event)
                {
                    $("#error_form").trigger("submit", [true]);

                }
            },

            {
                id:"errorCancelButton",
                text:"Cancel",
                click: function()
                {
                    $("#id_hidden1").val("");
                    $("#error_form").trigger("submit", [true]);
                }
            }
        ]
    }
            );
}
