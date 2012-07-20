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

    // click listeners
    $("#finish").live('click', function(event) {
        $("#finish").attr("disabled", true);
        //resetCleanupForm();
        if($("#id_num_users").attr("value") == 0){
            $("#wizard_form").attr("action","{% url gapps-index domain=domain %}");
            $("#wizard_form").trigger("submit", [true]);
        }
        else{
            $("#create_users_dialog").dialog('open');
        }
    });

    $("#id_num_users").live('change', function() {
        if ($("#id_num_users").attr("value") == 0){
            $("#div_create_for_all").attr("style", "display:block;");
            $("#id_create_for_all").attr("checked", true);
        }
        else {
            $("#div_create_for_all").attr("style", "display:none;");
            $("#id_create_for_all").attr("checked", false);
        }
    });

    if ($("#id_runtolimit_0").attr("checked")){
            $("#id_userlimit").attr("disabled", true);
        }

    $("input[name='runtolimit']").live('change', function() {
        if ($("#id_runtolimit_0").attr("checked")){
            $("#id_userlimit").attr("disabled", true);
        }
        else {
            $("#id_userlimit").attr("disabled", false);
        }
    });

}

function setupPopDialogs()
{
    // enduser dialogs
    $("#create_users_dialog").dialog(
    {
        autoOpen: false,
        width: 550,
        resizable: false,
        modal: true,
        closeOnEscape: false,
        draggable: false,
        open: function(event, ui){},//resetCleanupForm();},
        buttons: [
            {
                id:"wizardStartButton",
                text:"Submit",
                click:function(event)
                {
                    checkForm(event)

                }
            },

            {
                id:"wizardCancelButton",
                text:"Close",
                click: function()
                {
                    $(this).dialog("close");
                    $("#close_button").attr("disabled", false);
                    $("#finish").attr("disabled", false);
                }
            }
        ]
    }
            );
}

/* all flow logic */
function checkForm(event)
{
    
    $.ajax({
        type: 'POST',
        url: "{% url gapps-domain-wizard-error domain=domain %}",
        data: {username: $("#id_diag_username").val().toString(), password: $("#id_diag_password").val().toString()},
        dataType: 'json',
        success: function(data)
        {
            if (data.length == 0)
            {
                // proceed with regular flow
                //checkForm(undefined);
                $("#id_hidden1").val($("#id_diag_username").val());
                $("#id_hidden2").val($("#id_diag_password").val());
                //return true;
                $("#wizard_form").attr("action","{% url gapps-index domain=domain %}");
                $("#wizard_form").trigger("submit", [true]);
            }
            else
            {
                if (data[0].indexOf("unfortunately") != -1){
                    //can't create users do actions on form etc.
                    //setUserCheckText(data);
                    //$("#username_error_msg").html('test');
                    $("#id_hidden1").val($("#id_diag_username").val());
                    $("#id_hidden2").val($("#id_diag_password").val());
                    $("#id_hidden3").val(true);
                    //return true;
                    $("#wizard_form").attr("action","{% url gapps-index domain=domain %}");
                    $("#wizard_form").trigger("submit", [true]);

                    //OLD WAY
                    //can't create users do actions on form etc.
                    //setUserCheckText(data);
                    //$("#username_error_msg").html('test');
//                    $("#id_num_users").attr("value", "0");
//                    $("#id_num_users").attr("disabled", true);
//                    $("#create_users_error_msg").html('<ul class="errorlist"><li class="ui-corner-all">' + data[0] + ' <a href="{% url gapps-domain-wizard-learn-more domain=domain %}">Learn More</a></li></ul>');
//                    $("#div_create_for_all").attr("style", "display:block;");
//                    $("#id_create_for_all").attr("checked", true)
//                    $("#create_users_dialog").dialog("close");
//                    $("#close_button").attr("disabled", false);
//                    $("#finish").attr("disabled", false);
//                    return false;
                }
                else{
                    //invalid user/pass error update error message
                    $("#username_error_msg").html('<ul class="errorlist"><li class="ui-corner-all">' + data[0] + '</li></ul>');
                    //$("#user_check_dialog").dialog('open');
                    return false;

                }
            }
        }
    });
}
