import traceback
from flask_rq import job
from bookied_sync.lookup import Lookup
from .log import log
from .config import loadConfig
from .triggers import (
    CreateTrigger,
    ResultTrigger,
    InProgressTrigger,
    FinishTrigger
)
from . import exceptions


config = loadConfig()
lookup = Lookup(
    proposing_account=config.get("BOOKIE_PROPOSER"),
    approving_account=config.get("BOOKIE_APPROVER")
)

# We need to know the passphrase to unlock the wallet
if "passphrase" not in config:
    err = "No 'passphrase' found in configuration!"
    log.critical(err)
    raise ValueError(err)

if not lookup.wallet.created():
    err = "Please create a wallet and import the keys first!"
    log.critical(err)
    raise Exception(err)

lookup.wallet.unlock(config.get("passphrase"))


#
# Processing Job
#
@job
def process(
    message,
    **kwargs
):
    """ This process is called by the queue to process an actual message
        received. It instantiates from ``Process`` and let's the object deal
        with the message types.

        Hence, this method has the look and feel of a dispatcher!
    """
    assert isinstance(message, dict)
    assert "id" in message

    approver = kwargs.get("approver", None)
    if not approver:
        approver = message.get("approver", None)
    if approver:
        lookup.set_approving_account(approver)

    proposer = kwargs.get("proposer", None)
    if not proposer:
        proposer = message.get("proposer", None)
    if proposer:
        lookup.set_proposing_account(proposer)

    log.debug("Proposer account: {}".format(lookup.proposing_account))
    log.debug("Approver account: {}".format(lookup.approving_account))

    # Call
    call = message.get("call").lower()

    # Obtain arguments
    args = message.get("arguments")

    log.info("processing {} call with args {}".format(
        call, str(args)
    ))
    try:
        if call == "create":
            CreateTrigger(
                message,
                lookup_instance=lookup,
                config=config,
            ).trigger(args)

        elif call == "in_progress":
            InProgressTrigger(
                message,
                lookup_instance=lookup,
                config=config,
            ).trigger(args)

        elif call == "finish":
            FinishTrigger(
                message,
                lookup_instance=lookup,
                config=config,
            ).trigger(args)

        elif call == "result":
            ResultTrigger(
                message,
                lookup_instance=lookup,
                config=config,
            ).trigger(args)

        elif call == "unknown":
            pass

        else:
            log.error(
                "Received an unknown trigger {} with content: {}"
                .format(call, message)
            )

    except exceptions.EventDoesNotExistException:
        pass

    except exceptions.EventGroupClosedException:
        pass

    except exceptions.EventCannotOpenException:
        pass

    except exceptions.InsufficientIncidents:
        pass

    except exceptions.InsufficientEqualResults:
        pass

    except Exception as e:
        log.critical("Uncaught exception: {}\n\n{}".format(
            str(e),
            traceback.format_exc()))


#
# Approve my own Proposals
#
@job
def approve(*args, **kwargs):
    """ This process is meant to approve proposals that I have created.

        The reason for this is that proposals created by accountA are not
        automatically also approved by accountA and need an explicit approval.
    """
    from peerplays.account import Account
    from peerplays.proposal import Proposals
    from .config import loadConfig

    config = loadConfig()

    myapprover = kwargs.get("approver", None)
    if not myapprover:
        myapprover = config.get("BOOKIE_APPROVER")

    myproposer = kwargs.get("proposer", None)
    if not myproposer:
        myproposer = config.get("BOOKIE_PROPOSER")

    log.info(
        "Testing for pending proposals "
        "created by {} that we could approve by {}"
        .format(myproposer, myapprover))

    peerplays = lookup.peerplays
    proposals = Proposals("witness-account", peerplays_instance=peerplays)
    approver = Account(myapprover, peerplays_instance=peerplays)
    for proposal in proposals:
        proposer = Account(
            proposal.proposer,
            peerplays_instance=peerplays)
        if (
            proposer["name"] == myproposer and
            approver["id"] not in proposal["available_active_approvals"]
        ):
            log.info(
                "Proposal {} has been proposed by {}. Approving it!".format(
                    proposal["id"],
                    myproposer))
            log.info(peerplays.approveproposal(
                proposal["id"],
                account=myapprover
            ))
